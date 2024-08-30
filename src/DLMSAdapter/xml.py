from dataclasses import dataclass, field
from itertools import count
import copy
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
import logging
from DLMS_SPODES.cosem_interface_classes.collection import Collection, ServerId, ServerVersion, cst, ClassID, ic, ut, cdt, AssociationLN, Template
from DLMS_SPODES.cosem_interface_classes.association_ln.ver0 import ObjectListElement, AttributeAccessItem, AccessMode, is_attr_writable
from DLMS_SPODES.cosem_interface_classes import implementations as impl, collection
from DLMS_SPODES.version import AppVersion as SemVer
from DLMS_SPODES import exceptions as exc
from .main import Adapter


logger = logging.getLogger(__name__)


class AdapterException(Exception):
    """"""


root: Path = Path("..")
"""root for file as example"""
template_path = root / "Template"
types_path = root / "Types"
if not types_path.exists():
    types_path.mkdir()


@dataclass
class Xml40(Adapter):
    _root_tag: str = field(init=False, default="Objects")
    _template_root_tag: str = field(init=False, default="template.objects")
    keep_path: Path = field(init=False, default=root / "XML_devices")
    template_path: Path = field(init=False, default=root / "Templates")

    def __post_init__(self):
        if not self.keep_path.exists():
            self.keep_path.mkdir()
        if not self.template_path.exists():
            self.template_path.mkdir()
    @classmethod
    def get_version(cls) -> SemVer:
        return SemVer(4, 1)

    def __get_root_node(self, col: Collection) -> ET.Element:
        root_node = ET.Element(self._root_tag, attrib={"version": str(self.get_version())})
        ET.SubElement(root_node, 'dlms_ver').text = str(col.dlms_ver)
        ET.SubElement(root_node, 'country').text = str(col.country.value)
        if col.country_ver:
            ET.SubElement(root_node, 'country_ver').text = str(col.country_ver)
        if col.manufacturer is not None:
            ET.SubElement(root_node, 'manufacturer').text = col.manufacturer.decode("utf-8")
        if col.server_id is not None:
            ET.SubElement(root_node, 'server_type').text = col.server_id.value.encoding.hex()
        if col.server_ver is not None:
            ET.SubElement(root_node, 'server_ver', attrib={"instance": "1"}).text = str(col.server_ver.get_semver())
        return root_node

    def create_type(self, col: Collection):
        if not isinstance(col.manufacturer, bytes):
            raise AdapterException(F"{col} hasn't manufacturer parameter")
        if not isinstance(col.server_id, ServerId):
            raise AdapterException(F"{col} hasn't {ServerId.__class__.__name__} parameter")
        if not isinstance(col.server_ver, ServerVersion):
            raise AdapterException(F"{col} hasn't {ServerVersion.__class__.__name__} parameter")
        root_node = self.__get_root_node(col)
        objs: dict[cst.LogicalName, set[int]] = dict()
        """key: LN, value: not writable and readable container"""
        for ass in filter(lambda it: it.logical_name.e != 0, col.get_objects_by_class_id(ClassID.ASSOCIATION_LN)):
            if ass.object_list is None:
                logger.warning(F"for {ass} got empty <object_list>. skip it")
                continue
            for obj_el in ass.object_list:
                if str(obj_el.logical_name) in ("0.0.40.0.0.255", "0.0.42.0.0.255"):
                    """skip LDN and current_association"""
                    continue
                elif obj_el.logical_name in objs:
                    """"""
                else:
                    objs[obj_el.logical_name] = set()
                for access in obj_el.access_rights.attribute_access[1:]:  # without ln
                    if not access.access_mode.is_writable() and access.access_mode.is_readable():
                        objs[obj_el.logical_name].add(int(access.attribute_id))
        o2 = list()
        """container sort by AssociationLN first"""
        for ln in objs.keys():
            obj = col.get_object(ln)
            if obj.CLASS_ID == ClassID.ASSOCIATION_LN:
                o2.insert(0, obj)
            else:
                o2.append(obj)
        for obj in o2:
            object_node = ET.SubElement(root_node, "obj", attrib={'ln': str(obj.logical_name.get_report().msg)})
            if obj.CLASS_ID == ClassID.ASSOCIATION_LN:
                ET.SubElement(object_node, "ver").text = str(obj.VERSION)
            v = objs[obj.logical_name]
            for i, attr in filter(lambda it: it[0] != 1, obj.get_index_with_attributes()):
                el: ic.ICAElement = obj.get_attr_element(i)
                if el.classifier == ic.Classifier.STATIC and ((i in v) or el.DATA_TYPE == impl.profile_generic.CaptureObjectsDisplayReadout):
                    if attr is None:
                        logger.error(F"for {obj} attr: {i} not set, value is absense")
                    else:
                        ET.SubElement(object_node, "attr", attrib={"i": str(i)}).text = attr.encoding.hex()
                elif isinstance(el.DATA_TYPE, ut.CHOICE):  # need keep all CHOICES types if possible
                    if attr is None:
                        logger.error(F"for {obj} attr: {i} type not set, value is absense")
                    else:
                        ET.SubElement(object_node, "attr", attrib={"i": str(i)}).text = str(attr.TAG[0])
                else:
                    logger.info(F"for {obj} attr: {i} value not need. skipped")
            if len(object_node) == 0:
                root_node.remove(object_node)
        # TODO: '<!DOCTYPE ITE_util_tree SYSTEM "setting.dtd"> or xsd
        xml_string = ET.tostring(root_node, encoding='cp1251', method='xml')
        if not (man_path := types_path / col.manufacturer.decode("ascii")).exists():
            man_path.mkdir()
        if not (type_path := man_path / col.server_id.value.encoding.hex()).exists():
            type_path.mkdir()
        ver_path = type_path / F"{col.server_ver.get_semver()}.typ"
        with open(ver_path, "wb") as f:
            f.write(xml_string)

    def __get_keep_path(self, col: Collection) -> Path:
        if (ldn := col.LDN.value) is None:
            raise exc.EmptyObj(F"No LDN value in collection")
        return (self.keep_path / ldn.contents.hex()).with_suffix(".xml")

    def keep_data(self, col: Collection, ass_id: int = 3) -> bool:
        path = self.__get_keep_path(col)
        root_node = self.__get_root_node(col)
        is_empty: bool = True
        parent_col = self.get_collection(
            m=col.manufacturer,
            sid=col.server_id,
            ver=col.server_ver)
        obj_list_el: ObjectListElement
        a_a: AttributeAccessItem
        for obj_list_el in col.getASSOCIATION(ass_id).object_list:
            obj = col.get_object(obj_list_el.logical_name)
            parent_obj = parent_col.get_object(obj_list_el.logical_name)
            object_node = None
            for a_a in obj_list_el.access_rights.attribute_access:
                if (i := int(a_a.attribute_id)) == 1:
                    """skip ln"""
                elif obj.get_attr_element(i).classifier == ic.Classifier.DYNAMIC:
                    """skip DYNAMIC attributes"""
                elif (attr := obj.get_attr(i)) is None:
                    """skip empty attributes"""
                elif parent_obj.get_attr(i) == attr:
                    """skip not changed attr value"""
                else:
                    is_empty = False
                    if object_node is None:
                        object_node = ET.SubElement(root_node, "object", attrib={'ln': str(obj.logical_name)})
                    ET.SubElement(object_node, "attr", attrib={'index': str(i)}).text = attr.encoding.hex()
        if not is_empty:
            # TODO: '<!DOCTYPE ITE_util_tree SYSTEM "setting.dtd"> or xsd
            xml_string = ET.tostring(root_node, encoding='cp1251', method='xml')
            with open(path, "wb") as f:
                f.write(xml_string)
        else:
            logger.warning("nothing save. all attributes according with origin collection")
        return not is_empty

    def get_data(self, col: Collection):
        path = self.__get_keep_path(col)
        tree = ET.parse(path)
        root_node = tree.getroot()
        if root_node.tag != self._root_tag:
            raise ValueError(F"ERROR: Root tag got {root_node.tag}, expected {self._root_tag}")
        root_version = SemVer.from_str(root_node.attrib.get('version', '1.0.0'))
        if (dlms_ver := root_node.findtext("dlms_ver")) is not None:
            col.set_dlms_ver(int(dlms_ver))
        if (country := root_node.findtext("country")) is not None:
            col.set_country(collection.CountrySpecificIdentifiers(int(country)))
        if (country_ver := root_node.findtext("country_ver")) is not None:
            col.set_country_ver(ServerVersion(
                par=b'\x00\x00\x60\x01\x06\xff\x02',  # 0.0.96.1.6.255:2
                value=cdt.OctetString(bytearray(country_ver.encode(encoding="ascii")))
            ))
        if (manufacturer := root_node.findtext("manufacturer")) is not None:
            col.set_manufacturer(manufacturer.encode("utf-8"))
        if (server_id := root_node.findtext("server_type")) is not None:
            col.set_server_id(ServerId(
                par=b'\x00\x00\x60\x01\x01\xff\x02',  # 0.0.96.1.1.255:2
                value=cdt.get_instance_and_pdu_from_value(bytes.fromhex(server_id))[0]
            ))
        if (server_ver := root_node.findtext("server_ver")) is not None:
            col.set_server_ver(ServerVersion(
                par=b'\x00\x00\x00\x02\x00\xff\x02',
                value=cdt.OctetString(bytearray(server_ver.encode(encoding="ascii")))
            ))
        logger.info(F"Версия: {root_version}, {path=}")
        match root_version:
            case SemVer(3, 1 | 2):
                for obj in root_node.findall("object"):
                    ln: str = obj.attrib.get('ln', 'is absence')
                    logical_name: cst.LogicalName = cst.LogicalName.from_obis(ln)
                    if not col.is_in_collection(logical_name):
                        logger.error(F"got object with {ln=} not find in collection. Skip it attribute values")
                        continue
                    else:
                        new_object = col.get_object(logical_name)
                    indexes: list[int] = list()
                    """ got attributes indexes for current object """
                    for attr in obj.findall('attribute'):
                        index: str = attr.attrib.get('index')
                        if index.isdigit():
                            indexes.append(int(index))
                        else:
                            raise ValueError(F'ERROR: for obj with {ln=} got index {index} and it is not digital')
                        try:
                            new_object.set_attr(indexes[-1], bytes.fromhex(attr.text))
                        except exc.NoObject as e:
                            logger.error(F"Can't fill {new_object} attr: {indexes[-1]}. Skip. {e}.")
                            break
                        except exc.ITEApplication as e:
                            logger.error(F"Can't fill {new_object} attr: {indexes[-1]}. {e}")
                        except IndexError:
                            logger.error(F'Object "{new_object}" not has attr: {index}')
                        except TypeError as e:
                            logger.error(F'Object {new_object} attr:{index} do not write, encoding wrong : {e}')
                        except ValueError as e:
                            logger.error(F'Object {new_object} attr:{index} do not fill: {e}')
                        except AttributeError as e:
                            logger.error(F'Object {new_object} attr:{index} do not fill: {e}')
            case SemVer(4, 0 | 1):
                for obj in root_node.findall("object"):
                    ln: str = obj.attrib.get("ln", 'is absence')
                    logical_name: cst.LogicalName = cst.LogicalName(ln)
                    if not col.is_in_collection(logical_name):
                        raise ValueError(F"got object with {ln=} not find in collection. Abort attribute setting")
                    else:
                        new_object = col.get_object(logical_name)
                        for attr in obj.findall("attr"):
                            index: int = int(attr.attrib.get("index"))
                            try:
                                new_object.set_attr(index, bytes.fromhex(attr.text))
                            except exc.NoObject as e:
                                logger.error(F"Can't fill {new_object} attr: {index}. Skip. {e}.")
                                break
                            except exc.ITEApplication as e:
                                logger.error(F"Can't fill {new_object} attr: {index}. {e}")
                            except IndexError:
                                logger.error(F'Object "{new_object}" not has attr: {index}')
                            except TypeError as e:
                                logger.error(F'Object {new_object} attr:{index} do not write, encoding wrong : {e}')
                            except ValueError as e:
                                logger.error(F'Object {new_object} attr:{index} do not fill: {e}')
                            except AttributeError as e:
                                logger.error(F'Object {new_object} attr:{index} do not fill: {e}')
            case _ as error:
                raise exc.VersionError(error, additional='Xml')

    def get_collection(self,
                       m: bytes,
                       sid: ServerId,
                       ver: ServerVersion) -> Collection:
        path = get_col_path(m, sid, ver)
        tree = ET.parse(path)
        r_n = tree.getroot()
        new = Collection(
            dlms_ver=int(r_n.findtext("dlms_ver", "6")),
            country=collection.CountrySpecificIdentifiers(int(r_n.findtext("country", "7"))),
            man=r_n.findtext("manufacturer").encode("utf-8"),
            s_id=ServerId(
                par=b'\x00\x00\x60\x01\x01\xff\x02',
                value=cdt.get_instance_and_pdu_from_value(bytes.fromhex(r_n.findtext("server_type")))[0]),
            s_ver=ver,
            c_ver=ServerVersion(
                par=b'\x00\x00\x00\x02\x00\xff\x02',
                value=cdt.OctetString(bytearray(r_n.findtext("server_ver").encode(encoding="ascii"))))
        )
        if r_n.tag != self._root_tag:
            raise ValueError(F"ERROR: Root tag got {r_n.tag}, expected {self._root_tag}")
        root_version: SemVer = SemVer.from_str(r_n.attrib.get('version', '1.0.0'))
        logger.info(F'Версия: {root_version}, {path=}')
        match root_version:
            case SemVer(3, 0 | 1 | 2):
                attempts: iter = count(3, -1)
                """ attempts counter """
                while len(r_n) != 0 and next(attempts):
                    logger.info(F'{attempts=}')
                    for obj in r_n.findall('object'):
                        ln: str = obj.attrib.get('ln', 'is absence')
                        class_id: str = obj.findtext('class_id')
                        if not class_id:
                            logger.warning(F"skip create DLMS {ln} from Xml. Class ID is absence")
                            continue
                        version: str | None = obj.findtext('version')
                        try:
                            logical_name: cst.LogicalName = cst.LogicalName.from_obis(ln)
                            if not new.is_in_collection(logical_name):
                                new_object = new.add(class_id=ut.CosemClassId(class_id),
                                                     version=None if version is None else cdt.Unsigned(version),
                                                     logical_name=logical_name)
                            else:
                                new_object = new.get_object(logical_name.contents)
                        except TypeError as e:
                            logger.error(F'Object {obj.attrib["name"]} not created : {e}')
                            continue
                        except ValueError as e:
                            logger.error(F'Object {obj.attrib["name"]} not created. {class_id=} {version=} {ln=}: {e}')
                            continue
                        indexes: list[int] = list()
                        """ got attributes indexes for current object """
                        for attr in obj.findall('attribute'):
                            index: str = attr.attrib.get('index')
                            if index.isdigit():
                                indexes.append(int(index))
                            else:
                                raise ValueError(F'ERROR: for {new_object.logical_name if new_object is not None else ""} got index {index} and it is not digital')
                            try:
                                match len(attr.text), new_object.get_attr_element(indexes[-1]).DATA_TYPE:
                                    case 1 | 2, ut.CHOICE():
                                        if new_object.get_attr(indexes[-1]) is None:
                                            new_object.set_attr(indexes[-1], int(attr.text))
                                        else:
                                            """not need set"""
                                    case 1 | 2, data_type if data_type.TAG[0] == int(attr.text): """ ordering by old"""
                                    case 1 | 2, data_type:                                       raise ValueError(F'Got {attr.text} attribute Tag, expected {data_type}')
                                    case _:
                                        record_time: str = attr.attrib.get('record_time')
                                        if record_time is not None:
                                            new_object.set_record_time(indexes[-1], bytes.fromhex(record_time))
                                        new_object.set_attr(indexes[-1], bytes.fromhex(attr.text))
                                obj.remove(attr)
                            except ut.UserfulTypesException as e:
                                if attr.attrib.get("forced", None):
                                    new_object.set_attr_force(indexes[-1], cdt.get_common_data_type_from(int(attr.text).to_bytes(1, "big"))())
                                logger.warning(F"set to {new_object} attr: {indexes[-1]} forced value after. {e}.")
                            except exc.NoObject as e:
                                logger.error(F"Can't fill {new_object} attr: {indexes[-1]}. Skip. {e}.")
                                break
                            except exc.ITEApplication as e:
                                logger.error(F"Can't fill {new_object} attr: {indexes[-1]}. {e}")
                            except IndexError:
                                logger.error(F'Object "{new_object}" not has attr: {index}')
                            except TypeError as e:
                                logger.error(F'Object {new_object} attr:{index} do not write, encoding wrong : {e}')
                            except ValueError as e:
                                logger.error(F'Object {new_object} attr:{index} do not fill: {e}')
                            except AttributeError as e:
                                logger.error(F'Object {new_object} attr:{index} do not fill: {e}')
                        if len(obj.findall('attribute')) == 0:
                            r_n.remove(obj)
                    logger.info(F'Not parsed DLMS objects: {len(r_n)}')
            case SemVer(4, 0 | 1):
                attempts: iter = count(3, -1)
                """ attempts counter """
                while len(r_n) != 0 and next(attempts):
                    logger.info(F'{attempts=}')
                    for obj in r_n.findall("obj"):
                        ln: str = obj.attrib.get('ln', 'is absence')
                        version: str | None = obj.findtext("ver")
                        try:
                            logical_name: cst.LogicalName = cst.LogicalName.from_obis(ln)
                            if version:  # only for AssociationLN
                                new_object: AssociationLN = new.add_if_missing(
                                    class_id=ClassID.ASSOCIATION_LN,
                                    version=cdt.Unsigned(version),
                                    logical_name=logical_name)
                                new.add_if_missing(  # current association with know version
                                    class_id=ClassID.ASSOCIATION_LN,
                                    version=cdt.Unsigned(version),
                                    logical_name=cst.LogicalName.from_obis("0.0.40.0.0.255"))
                            else:
                                new_object = new.get_object(logical_name.contents)
                        except TypeError as e:
                            logger.error(F'Object {obj.attrib["ln"]} not created : {e}')
                            continue
                        except ValueError as e:
                            logger.error(F'Object {obj.attrib["ln"]} not created. {version=} {ln=}: {e}')
                            continue
                        for attr in obj.findall("attr"):
                            i: int = int(attr.attrib.get("i"))
                            try:
                                if len(attr.text) <= 2:  # set only type with default value
                                    data_type = new_object.get_attr_element(i).DATA_TYPE
                                    if isinstance(data_type, ut.CHOICE):
                                        new_object.set_attr(i, int(attr.text))
                                    elif data_type.TAG[0] == int(attr.text):
                                        """ ordering by old"""
                                    else:
                                        raise ValueError(F'Got {attr.text} attribute Tag, expected {data_type}')
                                else:  # set common value
                                    new_object.set_attr(i, bytes.fromhex(attr.text))
                                    if new_object.CLASS_ID == ClassID.ASSOCIATION_LN and i == 2:  # setup new root_node from AssociationLN.object_list
                                        for obj_el in new_object.object_list:
                                            # obj_el: ObjectListElement
                                            new.add_if_missing(
                                                class_id=obj_el.class_id,
                                                version=obj_el.version,
                                                logical_name=obj_el.logical_name)
                                obj.remove(attr)
                            except ut.UserfulTypesException as e:
                                if attr.attrib.get("forced", None):
                                    new_object.set_attr_force(i, cdt.get_common_data_type_from(int(attr.text).to_bytes(1, "big"))())
                                logger.warning(F"set to {new_object} attr: {i} forced value after. {e}.")
                            except exc.NoObject as e:
                                logger.error(F"Can't fill {new_object} attr: {i}. Skip. {e}.")
                                break
                            except exc.ITEApplication as e:
                                logger.error(F"Can't fill {new_object} attr: {i}. {e}")
                            except IndexError:
                                logger.error(F'Object "{new_object}" not has attr: {i}')
                            except TypeError as e:
                                logger.error(F'Object {new_object} attr:{i} do not write, encoding wrong : {e}')
                            except ValueError as e:
                                logger.error(F'Object {new_object} attr:{i} do not fill: {e}')
                            except AttributeError as e:
                                logger.error(F'Object {new_object} attr:{i} do not fill: {e}')
                        if len(obj.findall("attr")) == 0:
                            r_n.remove(obj)
                    logger.info(F'Not parsed DLMS root_node: {len(r_n)}')
        return new

    def __get_template_root_node(self,
                                 collections: list[Collection]) -> ET.Element:
        r_n = ET.Element(self._template_root_tag, attrib={"version": str(self.get_version())})
        """root node"""
        ET.SubElement(r_n, 'dlms_ver').text = str(collections[0].dlms_ver)
        ET.SubElement(r_n, 'country').text = str(collections[0].country.value)
        ET.SubElement(r_n, 'country_ver').text = str(collections[0].country_ver)
        for col in collections:
            manufacture_node = ET.SubElement(r_n, 'manufacturer')
            manufacture_node.text = col.manufacturer.decode("utf-8")
            server_type_node = ET.SubElement(manufacture_node, 'server_type')
            server_type_node.text = col.server_id.value.encoding.hex()
            server_ver_node = ET.SubElement(server_type_node, 'server_ver', attrib={"instance": "1"})
            server_ver_node.text = str(col.server_ver.get_semver())
        return r_n

    def create_template(self,
                        name: str,
                        template: Template):
        used_copy = copy.deepcopy(template.used)
        r_n = self.__get_template_root_node(collections=template.collections)
        r_n.attrib["decode"] = "1"
        if template.verified:
            r_n.attrib["verified"] = "1"
        for col in template.collections:
            for ln, indexes in copy.copy(used_copy).items():
                try:
                    obj = col.get_object(ln)
                    object_node = ET.SubElement(
                        r_n,
                        "object",
                        attrib={"ln": str(obj.logical_name)})
                    for i in tuple(indexes):
                        attr = obj.get_attr(i)
                        if isinstance(attr, cdt.CommonDataType):
                            attr_el = ET.SubElement(
                                object_node,
                                "attr",
                                {"name": obj.get_attr_element(i).NAME,
                                 "index": str(i)})
                            if isinstance(attr, cdt.SimpleDataType):
                                attr_el.text = str(attr)
                            elif isinstance(attr, cdt.ComplexDataType):
                                attr_el.attrib["type"] = "array" if attr.TAG == b'\x01' else "struct"  # todo: make better
                                stack: list = [(attr_el, "attr_el_name", iter(attr))]
                                while stack:
                                    node, a_name, value_it = stack[-1]
                                    value = next(value_it, None)
                                    if value:
                                        if not isinstance(a_name, str):
                                            a_name = next(a_name).NAME
                                        if isinstance(value, cdt.Array):
                                            stack.append((ET.SubElement(node,
                                                                        "array",
                                                                        attrib={"name": a_name}), "ar_name", iter(value)))
                                        elif isinstance(value, cdt.Structure):
                                            stack.append((ET.SubElement(node, "struct"), iter(value.ELEMENTS), iter(value)))
                                        else:
                                            ET.SubElement(node,
                                                          "simple",
                                                          attrib={"name": a_name}).text = str(value)
                                    else:
                                        stack.pop()
                            indexes.remove(i)
                        else:
                            logger.error(F"skip record {obj}:attr={i} with value={attr}")
                    if len(indexes) == 0:
                        used_copy.pop(ln)
                except exc.NoObject as e:
                    logger.warning(F"skip obj with {ln=} in {template.collections.index(col)} collection: {e}")
                    continue
            if len(used_copy) == 0:
                logger.info(F"success decoding: used {template.collections.index(col) + 1} from {len(template.collections)} collections")
                break
        if len(used_copy) != 0:
            raise ValueError(F"failed decoding: {used_copy}")
        with open(
                (self.template_path / name).with_suffix(".xml"),
                mode="wb") as f:
            f.write(ET.tostring(
                element=r_n,
                encoding="utf-8",
                method="xml",
                xml_declaration=True))

    def get_template(self, name: str) -> Template:
        path = (self.template_path / name).with_suffix(".xml")
        used: collection.UsedAttributes = dict()
        cols = list()
        tree = ET.parse(path)
        r_n = tree.getroot()
        if r_n.tag != self._template_root_tag:
            raise ValueError(F"ERROR: Root tag got {r_n.tag}, expected {self._template_root_tag}")
        root_version: SemVer = SemVer.from_str(r_n.attrib.get('version', '1.0.0'))
        logger.info(F'Версия: {root_version}, {path=}')
        for manufacturer_node in r_n.findall("manufacturer"):
            for server_type_node in manufacturer_node.findall("server_type"):
                for server_ver_node in server_type_node.findall("server_ver"):
                    cols.append(self.get_collection(
                        m=manufacturer_node.text.encode("utf-8"),
                        sid=ServerId(
                            par=b'\x00\x00\x60\x01\x01\xff\x02',
                            value=cdt.get_instance_and_pdu_from_value(bytes.fromhex(server_type_node.text))[0]),
                        ver=ServerVersion(
                            par=b'\x00\x00\x00\x02\x00\xff\x02',
                            value=cdt.OctetString(bytearray(server_ver_node.text.encode(encoding="ascii")))
                        )
                    ))
        match root_version:
            case SemVer(4, 0 | 1):
                for obj in r_n.findall('object'):
                    ln: str = obj.attrib.get("ln", 'is absence')
                    obis = collection.OBIS.fromhex(ln)
                    objs: list[ic.COSEMInterfaceClasses] = list()
                    for col in cols:
                        if not col.is_in_collection(obis):
                            logger.warning(F"got object with {ln=} not find in collection: {col}")
                        else:
                            objs.append(col.get_object(obis))
                    used[obis] = set()
                    for attr in obj.findall("attr"):
                        index: int = int(attr.attrib.get("index"))
                        used[obis].add(index)
                        try:
                            match attr.attrib.get("type", "simple"):
                                case "simple":
                                    for new_object in objs:
                                        new_object.set_attr(index, attr.text)
                                case "array" | "struct":
                                    stack = [(list(), iter(attr))]
                                    while stack:
                                        v1, v2 = stack[-1]
                                        v = next(v2, None)
                                        if v is None:
                                            stack.pop()
                                        elif v.tag == "simple":
                                            v1.append(v.text)
                                        else:
                                            v1.append(list())
                                            stack.append((v1[-1], iter(v)))
                                    for new_object in objs:
                                        new_object.set_attr(index, v1)
                        except exc.ITEApplication as e:
                            logger.error(F"Can't fill {new_object} attr: {index}. {e}")
                        except IndexError:
                            logger.error(F'Object "{new_object}" not has attr: {index}')
                        except TypeError as e:
                            logger.error(F'Object {new_object} attr:{index} do not write, encoding wrong : {e}')
                        except ValueError as e:
                            logger.error(F'Object {new_object} attr:{index} do not fill: {e}')
                        except AttributeError as e:
                            logger.error(F'Object {new_object} attr:{index} do not fill: {e}')
            case _ as error:
                raise exc.VersionError(error, additional='Xml')
        return Template(
            collections=cols,
            used=used,
            verified=bool(int(r_n.findtext("verified", default="0"))))


def get_manufactures_container() -> dict[bytes, dict[bytes, dict[SemVer | cdt.CommonDataType, Path]]]:
    logger.info(F"create manufacturer configuration container")
    ret: dict[bytes, dict[bytes, dict[SemVer, Path]]] = dict()
    for m_path in types_path.iterdir():
        if m_path.is_dir():
            if len(m_path.name) == 3:
                man = m_path.name.encode("ascii")
            # elif len(m.name) == 6:
            #     man = bytes.fromhex(m.name)
            else:
                logger.warning(F"skip <{m_path}>: not recognized like manufacturer")
                continue
            ret[man] = dict()
            for sid_path in m_path.iterdir():
                if sid_path.is_dir():
                    ret[man][server_id := bytes.fromhex(sid_path.name)] = dict()
                    for ver_path in sid_path.iterdir():
                        if ver_path.is_file() and ver_path.suffix == ".typ":
                            if (v := SemVer.from_str(ver_path.stem)) == SemVer(0, 0, 0):  # todo: make Appversion other result if None
                                try:
                                    v = bytes.fromhex(ver_path.stem)
                                except ValueError as e:
                                    logger.error(F"skip type, wrong file name {ver_path}")
                                    continue
                            ret[man][server_id][v] = ver_path
    return ret


@lru_cache(maxsize=100)
def get_col_path(m: bytes, sid: ServerId, ver: ServerVersion) -> Path:
    """one recursion collection get way. ret: file, is_searched"""
    if (man := get_manufactures_container().get(m)) is None:
        raise AdapterException(F"no support manufacturer: {m}")
    elif (sid := man.get(sid.value.encoding)) is None:
        raise AdapterException(F"no support type {sid}, with manufacturer: {m}")
    elif path := sid.get(ver.get_semver()):
        logger.info(F"got collection from library by path: {path}")
        return path
    elif isinstance(semver := ver.get_semver(), SemVer) and (searched_version := semver.select_nearest(filter(lambda v: isinstance(v, SemVer), sid.keys()))):
        return sid.get(searched_version)
    else:
        raise AdapterException(F"no support version {ver} with manufacturer: {m}, identifier: {sid}")
