from itertools import count
from abc import ABC, abstractmethod
from typing import override
import re
import copy
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
import logging
from semver import Version as SemVer
from DLMS_SPODES.cosem_interface_classes.collection import Collection, ParameterValue, cst, ClassID, ic, ut, cdt, AssociationLN, Template
from DLMS_SPODES.cosem_interface_classes.association_ln.ver0 import ObjectListElement, AttributeAccessItem, AccessMode, is_attr_writable
from DLMS_SPODES.cosem_interface_classes import implementations as impl, collection
from DLMS_SPODES import exceptions as exc
from .main import Adapter, AdapterException

logger = logging.getLogger(__name__)
man6 = re.compile("([a-f, 0-9]{2}){3}")
hex_ = re.compile("([a-f, A-D, 0-9]{2})+")

root: Path = Path(".")
"""root for file as example"""
template_path = root / "Template"
types_path = root / "Types"
if not types_path.exists():
    types_path.mkdir()
KEEP_PATH: Path = root / "XML_devices"
TEMPLATE_PATH: Path = root / "Templates"
if not KEEP_PATH.exists():
    KEEP_PATH.mkdir()
if not TEMPLATE_PATH.exists():
    TEMPLATE_PATH.mkdir()


type Manufacturer = bytes
type FirmwareId = bytes
type FirmwareVer = bytes


class Base(Adapter, ABC):
    TYPE_ROOT_TAG: str

    @staticmethod
    def _get_keep_path(col: Collection) -> Path:
        if (ldn := col.LDN.value) is None:
            raise exc.EmptyObj(F"No LDN value in collection")
        return (KEEP_PATH / ldn.contents.hex()).with_suffix(".xml")

    @staticmethod
    def _get_template_path(name: str) -> Path:
        return (TEMPLATE_PATH / name).with_suffix(".tmp")

    @classmethod
    def _create_root_node(cls, tag: str) -> ET.Element:
        return ET.Element(tag, attrib={"version": str(cls.VERSION)})

    @classmethod
    @abstractmethod
    def _get_root_node(cls, col: Collection, tag: str) -> ET.Element:
        """create xml root node and fill header(parameters)"""

    @classmethod
    def get_data(cls, col: Collection):
        path = cls._get_keep_path(col)
        logger.info(F"find data {path=}")
        try:
            tree = ET.parse(path)
        except FileNotFoundError as e:
            raise AdapterException(F"not find data for {col}: {e}")
        cls.root2data(
            r_n=tree.getroot(),
            col=col
        )

    @classmethod
    def _is_header(cls, r_n: ET.Element, tag: str, ver: SemVer) -> bool:
        if r_n.tag == tag and (r_ver := SemVer.parse(r_n.attrib['version'])) == ver:
            logger.info(F"find version: {r_ver=}")
            return True
        else:
            return False

    @classmethod
    @abstractmethod
    def set_parameters(cls, r_n: ET.Element, col: Collection):
        """set or validate DLMS_VER, COUNTRY, COUNTRY_VER, MANUFACTURER, SERVER_ID, SERVER_VER with xml"""

    @classmethod
    @abstractmethod
    def root2data(cls, r_n: ET.Element, col: Collection):
        """fill collection data by r_n"""
        if not cls._is_header(r_n, Xml3.TYPE_ROOT_TAG, Xml3.VERSION):
            raise AdapterException(F"Unknown tag: {r_n.tag} with {r_n.attrib}")
        cls.set_parameters(r_n, col)
        ...

    @classmethod
    @abstractmethod
    def root2collection(cls, r_n: ET.Element, col: Collection):
        """fill collection by r_n"""
        if not cls._is_header(r_n, cls.TYPE_ROOT_TAG, cls.VERSION):
            raise AdapterException(F"Unknown tag: {r_n.tag} with {r_n.attrib}")
        cls.set_parameters(r_n, col)
        ...

    @staticmethod
    @abstractmethod
    @lru_cache(1)
    def get_manufactures_container() -> dict[bytes, dict[bytes, dict[SemVer, Path]]]:
        """return Map of Path by parameters"""

    @classmethod
    @abstractmethod
    @lru_cache(maxsize=100)
    def get_col_path(cls, m: bytes, f_id: ParameterValue, ver: ParameterValue) -> Path:
        """return Path by parameters"""

    @classmethod
    @lru_cache(maxsize=100)
    def _get_collection(cls,
                        m: bytes,
                        f_id: ParameterValue,
                        ver: ParameterValue) -> Collection:
        path = cls.get_col_path(m, f_id, ver)
        logger.info(F"find type {path=}")
        tree = ET.parse(path)
        new = cls.root2collection(
            r_n=tree.getroot(),
            col=Collection(
                man=m,
                f_id=f_id))
        return new

    @classmethod
    def get_collection(cls,
                       m: bytes,
                       f_id: ParameterValue,
                       ver: ParameterValue) -> Collection:
        """return copy of parent Collection"""
        new = cls._get_collection(m, f_id, ver).copy()
        new.set_firm_ver(ver)
        return new

    @classmethod
    def get_templates(cls) -> list[str]:
        raise AdapterException(F"{cls.__name__} not have <templates>")


class __GetCollectionMixin1(Base, ABC):
    """"""
    def get_collections(self) -> dict[bytes, [dict[bytes, tuple[bytes]]]]:
        ret: dict[bytes, [dict[bytes, tuple[bytes]]]] = dict()
        for m_k, m_v in self.get_manufactures_container().items():
            ret[m_k] = dict()
            for f_id_k, f_id_v in m_v.items():
                ret[m_k][f_id_k] = tuple(f_id_v.keys())
        return ret


class Xml3(__GetCollectionMixin1, Base):
    VERSION: SemVer = SemVer(3, 2)
    TYPE_ROOT_TAG: str = "Objects"
    DATA_ROOT_TAG: str = "Objects"
    TEMPLATE_ROOT_TAG: str = "template.objects"

    @classmethod
    def _get_root_node(cls, col: Collection, tag: str) -> ET.Element:
        r_n = cls._create_root_node(tag)
        ET.SubElement(r_n, "dlms_ver").text = str(col.dlms_ver)
        ET.SubElement(r_n, "country").text = str(col.country.value)
        if col.country_ver:
            ET.SubElement(r_n, "country_ver").text = str(SemVer.parse(col.country_ver.value.contents, optional_minor_and_patch=True))
        if col.manufacturer is not None:
            ET.SubElement(r_n, "manufacturer").text = col.manufacturer.decode("utf-8")
        if col.firm_id is not None:
            ET.SubElement(r_n, "server_type").text = col.firm_id.value.hex()
        if col.firm_ver is not None:
            ET.SubElement(r_n, "server_ver", attrib={"instance": "1"}).text = str(SemVer.parse(col.firm_ver.value[2:]))
        return r_n

    @classmethod
    def create_type(cls, col: Collection):
        raise AdapterException(F"not support <create_type> for {cls.VERSION}")

    @classmethod
    def keep_data(cls, col: Collection, ass_id: int = 3) -> bool:
        raise AdapterException(F"not support <keep_data> for {cls.VERSION}")

    @classmethod
    @override
    def _is_header(cls, r_n: ET.Element, tag: str, ver: SemVer) -> bool:
        r_ver = SemVer.parse(r_n.attrib['version'])
        if r_n.tag == tag and r_ver.major == ver.major and r_ver.minor <= ver.minor:
            logger.info(F"find version: {r_ver=}")
            return True
        else:
            return False

    @classmethod
    def set_parameters(cls, r_n: ET.Element, col: Collection):
        if (dlms_ver := r_n.findtext("dlms_ver")) is not None:
            col.set_dlms_ver(int(dlms_ver))
        if (country := r_n.findtext("country")) is not None:
            col.set_country(collection.CountrySpecificIdentifiers(int(country)))
        if (country_ver := r_n.findtext("country_ver")) is not None:
            col.set_country_ver(ParameterValue(
                par=b'\x00\x00\x60\x01\x06\xff\x02',  # 0.0.96.1.6.255:2
                value=cdt.OctetString(bytearray(country_ver.encode(encoding="ascii"))).encoding
            ))
        if (manufacturer := r_n.findtext("manufacturer")) is not None:
            col.set_manufacturer(manufacturer.encode("utf-8"))
        if (firm_id := r_n.findtext("server_type")) is not None:
            col.set_firm_id(ParameterValue(
                par=b'\x00\x00\x60\x01\x01\xff\x02',  # 0.0.96.1.1.255:2
                value=bytes.fromhex(firm_id)
            ))
        if (firm_ver := r_n.findtext("server_ver")) is not None:
            col.set_firm_ver(ParameterValue(
                par=b'\x00\x00\x00\x02\x01\xff\x02',
                value=firm_ver.encode(encoding="ascii")
            ))
        col.spec_map = col.get_spec()

    @classmethod
    def root2data(cls, r_n: ET.Element, col: Collection):
        if not cls._is_header(r_n, Xml3.TYPE_ROOT_TAG, Xml3.VERSION):
            raise AdapterException(F"Unknown tag: {r_n.tag} with {r_n.attrib}")
        cls.set_parameters(r_n, col)
        for obj in r_n.findall("object"):
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

    @classmethod
    def root2collection(cls, r_n: ET.Element, col: Collection):
        if not Xml3._is_header(r_n, Xml3.TYPE_ROOT_TAG, Xml3.VERSION):
            raise AdapterException(F"Unknown tag<{r_n.tag}> with {r_n.attrib}")
        cls.set_parameters(r_n, col)
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
                    if not col.is_in_collection(logical_name):
                        new_object = col.add(class_id=ut.CosemClassId(class_id),
                                             version=None if version is None else cdt.Unsigned(version),
                                             logical_name=logical_name)
                    else:
                        new_object = col.get_object(logical_name.contents)
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
                            case 1 | 2, data_type if data_type.TAG[0] == int(attr.text):
                                """ ordering by old"""
                            case 1 | 2, data_type:
                                raise ValueError(F'Got {attr.text} attribute Tag, expected {data_type}')
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
        return col

    @staticmethod
    @lru_cache(1)
    def get_manufactures_container() -> dict[bytes, dict[bytes, dict[SemVer, Path]]]:
        logger.info(F"use manufacturer configuration system {Xml3.__name__}")
        ret: dict[bytes, dict[bytes, dict[SemVer, Path]]] = dict()
        for m_path in types_path.iterdir():
            if m_path.is_dir():
                if len(m_path.name) == 3:
                    man = m_path.name.encode("ascii")
                # elif man6.fullmatch(m_path.name) is not None:
                #     man = bytes.fromhex(m_path.name)
                else:
                    logger.warning(F"skip <{m_path}>: not recognized like manufacturer")
                    continue
                ret[man] = dict()
                for sid_path in m_path.iterdir():
                    if sid_path.is_dir():
                        ret[man][firm_id := bytes.fromhex(sid_path.name)] = dict()
                        for ver_path in sid_path.iterdir():
                            if ver_path.is_file() and ver_path.suffix == ".typ":
                                try:
                                    v = SemVer.parse(ver_path.stem)
                                except ValueError as e:
                                    logger.error(F"skip type, wrong file name {ver_path}: {e}")
                                    continue
                                ret[man][firm_id][v] = ver_path
        return ret

    @classmethod
    @lru_cache(maxsize=100)
    def get_col_path(cls, m: bytes, f_id: ParameterValue, ver: ParameterValue) -> Path:
        """ret: file, is_searched"""
        if (man := cls.get_manufactures_container().get(m)) is None:
            raise AdapterException(F"no support manufacturer: {m}")
        elif (firm_id := man.get(f_id.value)) is None:
            raise AdapterException(F"no support type {f_id}, with manufacturer: {m}")
        elif path := firm_id.get(semver := SemVer.parse(ver.value[2:], True)):
            logger.info(F"got collection from library by {path=}")
            return path
        else:
            try:
                # todo: remove all compatible without MAX version
                return firm_id.get(max(filter(lambda v: v.is_compatible(semver), firm_id.keys())))
            except ValueError:
                raise AdapterException(F"no support version {ver} with manufacturer: {m}, identifier: {f_id}")

    @classmethod
    def create_template(cls,
                        name: str,
                        template: Template):
        raise AdapterException(F"not support <create_template> for {cls.VERSION}")

    @classmethod
    def get_template(cls, name: str) -> Template:
        raise AdapterException(F"not support <get_template> for {cls.VERSION}")


class Xml40(__GetCollectionMixin1, Base):
    VERSION: SemVer = SemVer(4, 0)
    TYPE_ROOT_TAG = Xml3.TYPE_ROOT_TAG
    DATA_ROOT_TAG = Xml3.DATA_ROOT_TAG
    TEMPLATE_ROOT_TAG = Xml3.TEMPLATE_ROOT_TAG

    @classmethod
    def _get_root_node(cls, col: Collection, tag: str) -> ET.Element:
        return Xml3._get_root_node(col, tag)

    @classmethod
    def set_parameters(cls, r_n: ET.Element, col: Collection):
        Xml3.set_parameters(r_n, col)

    @staticmethod
    def get_manufactures_container() -> dict[bytes, dict[bytes, dict[SemVer, Path]]]:
        return Xml3.get_manufactures_container()

    @classmethod
    def get_col_path(cls, m: bytes, f_id: ParameterValue, ver: ParameterValue) -> Path:
        return Xml3.get_col_path(m, f_id, ver)

    @classmethod
    def create_type(cls, col: Collection):
        Xml3.create_type(col)

    @classmethod
    def keep_data(cls, col: Collection, ass_id: int = 3) -> bool:
        return Xml3.keep_data(col)

    @classmethod
    def create_template(cls, name: str, template: Template):
        Xml3.create_template(name, template)

    @classmethod
    def get_template(cls, name: str) -> Template:
        return Xml3.get_template(name)

    @classmethod
    def root2data(cls, r_n: ET.Element, col: Collection):
        if not cls._is_header(r_n, Xml40.DATA_ROOT_TAG, Xml40.VERSION):
            return Xml3.root2data(r_n, col)
        cls.set_parameters(r_n, col)
        cls._fill_data40(r_n, col)

    @classmethod
    def _fill_data40(cls, r_n: ET.Element, col: Collection):
        for obj_el in r_n.findall("object"):
            ln: str = obj_el.attrib.get("ln", 'is absence')
            logical_name: cst.LogicalName = cst.LogicalName.from_obis(ln)
            if not col.is_in_collection(logical_name):
                raise ValueError(F"got object with {ln=} not find in collection. Abort attribute setting")
            else:
                obj = col.get_object(logical_name)
                for attr_el in obj_el.findall("attr"):
                    index: int = int(attr_el.attrib.get("index"))
                    try:
                        obj.set_attr(index, bytes.fromhex(attr_el.text))
                    except exc.NoObject as e:
                        logger.error(F"Can't fill {obj} attr: {index}. Skip. {e}.")
                        break
                    except exc.ITEApplication as e:
                        logger.error(F"Can't fill {obj} attr: {index}. {e}")
                    except IndexError:
                        logger.error(F'Object "{obj}" not has attr: {index}')
                    except TypeError as e:
                        logger.error(F'Object {obj} attr:{index} do not write, encoding wrong : {e}')
                    except ValueError as e:
                        logger.error(F'Object {obj} attr:{index} do not fill: {e}')
                    except AttributeError as e:
                        logger.error(F'Object {obj} attr:{index} do not fill: {e}')

    @staticmethod
    def _fill_collection40(r_n: ET.Element, col: Collection):
        """fill created collection from xml"""
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
                        new_object: AssociationLN = col.add_if_missing(
                            class_id=ClassID.ASSOCIATION_LN,
                            version=cdt.Unsigned(version),
                            logical_name=logical_name)
                        col.add_if_missing(  # current association with know version
                            class_id=ClassID.ASSOCIATION_LN,
                            version=cdt.Unsigned(version),
                            logical_name=cst.LogicalName.from_obis("0.0.40.0.0.255"))
                    else:
                        new_object = col.get_object(logical_name.contents)
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
                                    col.add_if_missing(
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

    @classmethod
    def root2collection(cls, r_n: ET.Element, col: Collection):
        if not cls._is_header(r_n, Xml40.TYPE_ROOT_TAG, Xml40.VERSION):
            return Xml3.root2collection(r_n, col)
        cls.set_parameters(r_n, col)
        cls._fill_collection40(r_n, col)
        return col


class Xml41(__GetCollectionMixin1, Base):
    VERSION: SemVer = SemVer(4, 1)
    TYPE_ROOT_TAG = Xml3.TYPE_ROOT_TAG
    DATA_ROOT_TAG = Xml3.DATA_ROOT_TAG
    TEMPLATE_ROOT_TAG = Xml3.TEMPLATE_ROOT_TAG

    @classmethod
    def set_parameters(cls, r_n: ET.Element, col: Collection):
        Xml3.set_parameters(r_n, col)

    @staticmethod
    @lru_cache(1)
    def get_manufactures_container() -> dict[Manufacturer, dict[FirmwareId, dict[SemVer, Path]]]:
        return Xml3.get_manufactures_container()

    @classmethod
    def get_col_path(cls, m: bytes, f_id: ParameterValue, ver: ParameterValue) -> Path:
        return Xml3.get_col_path(m, f_id, ver)

    @classmethod
    def _get_root_node(cls, col: Collection, tag: str) -> ET.Element:
        return Xml3._get_root_node(col, tag)

    @classmethod
    def create_type(cls, col: Collection):
        root_node = cls._get_root_node(col, cls.TYPE_ROOT_TAG)
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
        if not (type_path := man_path / col.firm_id.value.hex()).exists():
            type_path.mkdir()
        ver_path = type_path / F"{SemVer.parse(col.firm_ver.value)}.typ"  # use
        with open(ver_path, "wb") as f:
            f.write(xml_string)
            cls.get_manufactures_container().cache_clear()

    @classmethod
    def keep_data(cls, col: Collection, ass_id: int = 3) -> bool:
        path = cls._get_keep_path(col)
        root_node = cls._get_root_node(col, cls.DATA_ROOT_TAG)
        is_empty: bool = True
        parent_col = cls._get_collection(
            m=col.manufacturer,
            f_id=col.firm_id,
            ver=col.firm_ver)
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
                        object_node = ET.SubElement(root_node, "object", attrib={'ln': obj.logical_name.get_report().msg})
                    ET.SubElement(object_node, "attr", attrib={'index': str(i)}).text = attr.encoding.hex()
        if not is_empty:
            # TODO: '<!DOCTYPE ITE_util_tree SYSTEM "setting.dtd"> or xsd
            xml_string = ET.tostring(root_node, encoding='cp1251', method='xml')
            with open(path, "wb") as f:
                f.write(xml_string)
        else:
            logger.warning("nothing save. all attributes according with origin collection")
        return not is_empty

    @classmethod
    def root2data(cls, r_n: ET.Element, col: Collection):
        if not cls._is_header(r_n, Xml41.DATA_ROOT_TAG, Xml41.VERSION):
            return Xml40.root2data(r_n, col)
        cls.set_parameters(r_n, col)
        Xml40._fill_data40(r_n, col)

    @classmethod
    def root2collection(cls, r_n: ET.Element, col: Collection):
        if not cls._is_header(r_n, Xml41.TYPE_ROOT_TAG, Xml41.VERSION):
            return Xml40.root2collection(r_n, col)
        cls.set_parameters(r_n, col)
        Xml40._fill_collection40(r_n, col)
        return col

    @classmethod
    def _get_template_root_node(cls,
                                collections: list[Collection]) -> ET.Element:
        r_n = cls._create_root_node(cls.TEMPLATE_ROOT_TAG)
        ET.SubElement(r_n, "dlms_ver").text = str(collections[0].dlms_ver)
        ET.SubElement(r_n, "country").text = str(collections[0].country.value)
        ET.SubElement(r_n, "country_ver").text = str(SemVer.parse(collections[0].country_ver.value.contents, optional_minor_and_patch=True))
        for col in collections:
            manufacture_node = ET.SubElement(r_n, "manufacturer")
            manufacture_node.text = col.manufacturer.decode("utf-8")
            server_type_node = ET.SubElement(manufacture_node, "server_type")
            server_type_node.text = col.firm_id.value.hex()
            firm_ver_node = ET.SubElement(server_type_node, "server_ver", attrib={"instance": "1"})
            firm_ver_node.text = str(SemVer.parse(col.firm_ver.value))
        return r_n

    @staticmethod
    def temp2root(r_n: ET.Element,
                  path: Path,
                  template: Template):
        used_copy = copy.deepcopy(template.used)
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
                        attrib={"ln": obj.logical_name.get_report().msg})
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
        with open(path, mode="wb") as f:
            f.write(ET.tostring(
                element=r_n,
                encoding="utf-8",
                method="xml",
                xml_declaration=True))

    @classmethod
    def create_template(cls,
                        name: str,
                        template: Template):
        cls.temp2root(
            r_n=cls._get_template_root_node(collections=template.collections),
            path=cls._get_template_path(name),
            template=template)

    @classmethod
    def get_template(cls, name: str) -> Template:
        path = cls._get_template_path(name)
        used: collection.UsedAttributes = dict()
        cols = list()
        tree = ET.parse(path)
        r_n = tree.getroot()
        if not cls._is_header(r_n, Xml41.TEMPLATE_ROOT_TAG, Xml41.VERSION):
            raise AdapterException(F"Unknown tag: {r_n.tag} with {r_n.attrib}")

        for manufacturer_node in r_n.findall("manufacturer"):
            for server_type_node in manufacturer_node.findall("server_type"):
                for firm_ver_node in server_type_node.findall("server_ver"):
                    cols.append(cls.get_collection(
                        m=manufacturer_node.text.encode("utf-8"),
                        f_id=ParameterValue(
                            par=b'\x00\x00\x60\x01\x01\xff\x02',
                            value=bytes.fromhex(server_type_node.text)
                        ),
                        ver=ParameterValue(
                            par=b'\x00\x00\x00\x02\x00\xff\x02',
                            value=cdt.OctetString(bytearray(firm_ver_node.text.encode(encoding="ascii"))).encoding
                        )
                    ))
        for obj in r_n.findall('object'):
            ln: str = obj.attrib.get("ln", 'is absence')
            obis = cst.LogicalName.from_obis(ln)
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
        return Template(
            collections=cols,
            used=used,
            verified=bool(int(r_n.findtext("verified", default="0"))))


class Xml50(__GetCollectionMixin1, Base):
    """"""
    VERSION = SemVer(5, 0)
    TYPE_ROOT_TAG = "DLMSServerType"
    DATA_ROOT_TAG = "DLMSServerData"
    TEMPLATE_ROOT_TAG: str = "DLMSServerTemplate"

    @classmethod
    def root2data(cls, r_n: ET.Element, col: Collection):
        if not cls._is_header(r_n, Xml50.DATA_ROOT_TAG, Xml50.VERSION):
            return Xml41.root2data(r_n, col)
        cls.set_parameters(r_n, col)
        Xml40._fill_data40(r_n, col)

    @classmethod
    def root2collection(cls, r_n: ET.Element, col: Collection):
        if not cls._is_header(r_n, Xml50.TYPE_ROOT_TAG, Xml50.VERSION):
            return Xml41.root2collection(r_n, col)
        cls.set_parameters(r_n, col)
        Xml40._fill_collection40(r_n, col)
        return col

    @classmethod
    def keep_data(cls, col: Collection, ass_id: int = 3) -> bool:
        path = cls._get_keep_path(col)
        root_node = cls._get_root_node(col, cls.DATA_ROOT_TAG)
        is_empty: bool = True
        parent_col = cls._get_collection(
            m=col.manufacturer,
            f_id=col.firm_id,
            ver=col.firm_ver)
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
                        object_node = ET.SubElement(root_node, "object", attrib={'ln': obj.logical_name.get_report().msg})
                    ET.SubElement(object_node, "attr", attrib={'index': str(i)}).text = attr.encoding.hex()
        if not is_empty:
            # TODO: '<!DOCTYPE ITE_util_tree SYSTEM "setting.dtd"> or xsd
            xml_string = ET.tostring(root_node, encoding="UTF-8", method="xml")
            with open(path, "wb") as f:
                f.write(xml_string)
        else:
            logger.warning("nothing save. all attributes according with origin collection")
        return not is_empty

    @staticmethod
    def get_template_node(node: ET.Element, tag: str, value: str) -> ET.Element:
        if (old := node.find(tag)) is not None and (old.findtext("value") == value):
            return old
        else:
            new = ET.SubElement(node, tag)
            ET.SubElement(new, "value").text = value
        return new

    @classmethod
    def get_template_node_param(cls, parent: ET.Element, tag: str, value: ParameterValue) -> ET.Element:
        if (old := parent.find(tag)) is not None and (old.findtext("value") == value.value.hex()) and (old.findtext("par") == value.par.hex()):
            return old
        else:
            return cls.parval2node(parent, tag, value)

    @staticmethod
    def parval2node(parent: ET.Element, tag: str, value: ParameterValue) -> ET.Element:
        new = ET.SubElement(parent, tag)
        ET.SubElement(new, "par").text = value.par.hex()
        ET.SubElement(new, "value").text = value.value.hex()
        return new

    @classmethod
    def _get_template_root_node(cls,
                                collections: list[Collection]) -> ET.Element:
        r_n = cls._create_root_node(cls.TEMPLATE_ROOT_TAG)
        for col in collections:
            man_n = cls.get_template_node(r_n, "manufacturer", str(col.manufacturer.hex()))
            firm_id_n = cls.get_template_node_param(man_n, "firm_id", col.firm_id)
            cls.get_template_node_param(firm_id_n, "firm_ver", col.firm_ver)
        return r_n

    @staticmethod
    def _get_template_path(name: str) -> Path:
        path = TEMPLATE_PATH / name
        if name.find('.') == -1:
            path = path.with_suffix(".xml")
        return path

    @classmethod
    def create_template(cls,
                        name: str,
                        template: Template):
        Xml41.temp2root(
            r_n=cls._get_template_root_node(collections=template.collections),
            path=cls._get_template_path(name),
            template=template)

    @staticmethod
    def node2parval(node: ET.Element) -> ParameterValue:
        return ParameterValue(
            par=bytes.fromhex(node.findtext("par")),
            value=bytes.fromhex(node.findtext("value"))
        )

    @classmethod
    def get_template(cls, name: str) -> Template:
        path = cls._get_template_path(name)
        r_n = ET.parse(path).getroot()
        used: collection.UsedAttributes = dict()
        cols = list()
        if not cls._is_header(r_n, Xml50.TEMPLATE_ROOT_TAG, Xml50.VERSION):
            return xml41.get_template(name)
        for man_n in r_n.findall("manufacturer"):
            for fid_n in man_n.findall("firm_id"):
                for fv_n in fid_n.findall("firm_ver"):
                    try:
                        cols.append(cls.get_collection(
                            m=bytes.fromhex(man_n.findtext("value")),
                            f_id=cls.node2parval(fid_n),
                            ver=cls.node2parval(fv_n),
                        ))
                    except AdapterException as e:
                        logger.error(F"collection with: {man_n}/{fid_n}/{fv_n} not load to Template")
                        continue
        for obj in r_n.findall('object'):
            ln: str = obj.attrib.get("ln", 'is absence')
            obis = cst.LogicalName.from_obis(ln)
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
        return Template(
            collections=cols,
            used=used,
            verified=bool(int(r_n.findtext("verified", default="0"))))

    @classmethod
    def set_parameters(cls, r_n: ET.Element, col: Collection):
        # todo: wrong from ver3.0
        if (dlms_ver := r_n.findtext("dlms_ver")) is not None:
            col.set_dlms_ver(int(dlms_ver))
        if (country := r_n.findtext("country")) is not None:
            col.set_country(collection.CountrySpecificIdentifiers(int(country)))
        if (country_ver_el := r_n.find("country_ver")) is not None:
            col.set_country_ver(cls.node2parval(country_ver_el))
        if (manufacturer := r_n.findtext("manufacturer")) is not None:
            col.set_manufacturer(bytes.fromhex(manufacturer))
        if (firm_id_el := r_n.find("firm_id")) is not None:
            col.set_firm_id(cls.node2parval(firm_id_el))
        if (firm_ver_el := r_n.find("firm_ver")) is not None:
            col.set_firm_ver(cls.node2parval(firm_ver_el))
        col.spec_map = col.get_spec()

    @classmethod
    @lru_cache(maxsize=100)
    def get_col_path(cls, m: bytes, f_id: ParameterValue, ver: ParameterValue) -> Path:
        """ret: file, is_searched"""
        if (man := cls.get_manufactures_container().get(m)) is None:
            raise AdapterException(F"no support manufacturer: {m}")
        elif (firm_id := man.get(f_id.value)) is None:
            raise AdapterException(F"no support type {f_id}, with manufacturer: {m}")
        elif (path := firm_id.get(ver.value)) is not None:
            logger.info(F"got collection from library by {path=}")
            return path
        elif SemVer.is_valid((ver_ := cdt.get_instance_and_pdu_from_value(ver.value)[0].contents).decode("utf-8", "ignore")):
            logger.warning(F"try find compatible version...")
            semver = SemVer.parse(ver_)
            for v in firm_id.keys():
                data, _ = cdt.get_instance_and_pdu_from_value(v)
                d = data.decode()
                if (
                    SemVer.is_valid(d.decode("utf-8", "ignore")) and
                    SemVer.parse(d, True) == semver
                ):
                    return firm_id[v]
            else:
                raise AdapterException(F"was no find compatible version {ver} with manufacturer: {m}, identifier: {f_id}")
        else:
            raise AdapterException(F"no support version {ver} with manufacturer: {m}, identifier: {f_id}")
            # raise Xml3.get_col_path(m, f_id, ver)

    @staticmethod
    @lru_cache(1)
    def get_manufactures_container() -> dict[Manufacturer, dict[FirmwareId, dict[FirmwareVer, Path]]]:
        logger.info(F"use manufacturer configuration system {Xml50.__name__}")
        ret = dict()
        for m_path in types_path.iterdir():
            if m_path.is_dir():
                if man6.fullmatch(m_path.name) is not None:
                    man = bytes.fromhex(m_path.name)
                else:
                    logger.warning(F"skip <{m_path}>: not recognized like manufacturer")
                    continue
                ret[man] = dict()
                for fid in m_path.iterdir():
                    if fid.is_dir() and hex_.fullmatch(fid.name):
                        ret[man][firm_id := bytes.fromhex(fid.name)] = dict()
                        for ver_path in fid.iterdir():
                            if ver_path.is_file() and ver_path.suffix == ".xml" and hex_.fullmatch(ver_path.stem):
                                ret[man][firm_id][bytes.fromhex(ver_path.stem)] = ver_path
        return ret

    @classmethod
    def get_version(cls) -> SemVer:
        return SemVer(5, 0)

    @classmethod
    def _get_root_node(cls, col: Collection, tag: str) -> ET.Element:
        r_n = cls._create_root_node(tag)
        ET.SubElement(r_n, "dlms_ver").text = str(col.dlms_ver)
        return cls._get_type_node(col, r_n)

    @classmethod
    def _get_type_node(cls, col: Collection, r_n: ET.Element) -> ET.Element:
        if col.country is not None:
            ET.SubElement(r_n, "country").text = str(col.country.value)
            if col.country_ver:
                cls.parval2node(r_n, "country_ver", col.country_ver)
        if col.manufacturer is not None:
            ET.SubElement(r_n, "manufacturer").text = col.manufacturer.hex()
            if col.firm_id is not None:
                cls.parval2node(r_n, "firm_id", col.firm_id)
                if col.firm_ver is not None:
                    cls.parval2node(r_n, "firm_ver", col.firm_ver)
        return r_n

    @classmethod
    def create_type(cls, col: Collection):
        if not isinstance(col.manufacturer, bytes):
            raise AdapterException(F"{col} hasn't manufacturer parameter")
        if not isinstance(col.firm_id, ParameterValue):
            raise AdapterException(F"{col} hasn't <Firmware ID> parameter")
        if not isinstance(col.firm_ver, ParameterValue):
            raise AdapterException(F"{col} hasn't <Firmware Version> parameter")
        root_node = cls._get_root_node(col, Xml50.TYPE_ROOT_TAG)
        objs: dict[cst.LogicalName, set[int]] = dict()
        """key: LN, value: not writable and readable container"""
        reduce_ln = collection.ln_pattern.LNPattern("0.0.(40,42).0.0.255")
        for ass in filter(lambda it: it.logical_name.e != 0, col.get_objects_by_class_id(ClassID.ASSOCIATION_LN)):
            if ass.object_list is None:
                logger.warning(F"for {ass} got empty <object_list>. skip it")
                continue
            for obj_el in ass.object_list:
                if reduce_ln == obj_el.logical_name:
                    """skip LDN and current_association"""
                    continue
                elif obj_el.logical_name in objs:
                    """"""
                else:
                    objs[obj_el.logical_name] = set()
                for access in obj_el.access_rights.attribute_access[1:]:  # without ln
                    if (
                        access.access_mode.is_readable()
                        and not access.access_mode.is_writable()
                    ):
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
        xml_string = ET.tostring(root_node, encoding="utf-8", method='xml')
        if not (man_path := types_path / col.manufacturer.hex()).exists():
            man_path.mkdir()
        if not (type_path := man_path / col.firm_id.value.hex()).exists():
            type_path.mkdir()
        ver_path = type_path / F"{col.firm_ver.value.hex()}.xml"
        with open(ver_path, "wb") as f:
            f.write(xml_string)
            cls.get_manufactures_container.cache_clear()

    @classmethod
    def get_templates(cls) -> list[str]:
        """return name with stem"""
        ret = list()
        for path in TEMPLATE_PATH.iterdir():
            if path.is_file() and path.suffix in (".xml", ".tmp"):
                ret.append(path.name)
        return ret


xml3 = Xml3()
xml4 = Xml40()
xml41 = Xml41()
xml50 = Xml50()
