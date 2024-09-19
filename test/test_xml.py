import unittest
from DLMS_SPODES.cosem_interface_classes import collection, overview
from DLMS_SPODES.types import cdt, cst
from src.DLMSAdapter.xml_ import Xml41, Xml40, Xml3, ET, xml50
import logging

server_1_4_15 = collection.ParameterValue(
        par=bytes.fromhex("0000000201ff02"),
        value=cdt.OctetString(bytearray(b"1.4.15")).encoding)
server_1_7_3 = collection.ParameterValue(
        par=bytes.fromhex("0000000201ff02"),
        value=cdt.OctetString(bytearray(b"1.7.3")).encoding)
server_1_7_4 = collection.ParameterValue(
        par=bytes.fromhex("0000000201ff02"),
        value=cdt.OctetString(bytearray(b"1.8.4")).encoding)
serID_M2M_1 = collection.ParameterValue(
        par=bytes.fromhex("0000600101ff02"),
        value=cdt.OctetString(bytearray(b'M2M_1')).encoding)
serID50_M2M_1 = collection.ParameterValue(
        par=bytes.fromhex("0000000200ff02"),
        value=(bytes.fromhex("090e5057524d5f4d324d5f315f46345f"))
)
serID_M2M_3 = collection.ParameterValue(
        par=bytes.fromhex("0000600101ff02"),
        value=cdt.OctetString(bytearray(b'M2M_3')).encoding)


colXXX = collection.Collection(
    man=b'XXX',
    f_id=collection.ParameterValue(b'1234567', cdt.OctetString(bytearray(b'M2M-1')).encoding),
    f_ver=collection.ParameterValue(b'1234560', cdt.OctetString(bytearray(b'1.4.2')).encoding)
)
clock_obj = colXXX.add(
    overview.ClassID.CLOCK,
    overview.Version.V0,
    cst.LogicalName.from_obis("0.0.1.0.0.255"))
clock_obj.set_attr(3, 120)

logger = logging.getLogger(__name__)
logger.level = logging.INFO


class TestType(unittest.TestCase):
    def test_create_adapter(self):
        adapter_ = xml50()

    def test_create_type(self):
        print(colXXX)
        xml50.create_type(colXXX)
        col = xml50.get_collection(colXXX.manufacturer, colXXX.firm_id, colXXX.firm_ver)
        print(col)

    def test_get_man(self):
        c = Xml3.get_manufactures_container()
        print(c)
        mans = xml50.get_collections()
        print(mans)

    def test_get_obj_list(self):
        # todo: don't work now
        col = Xml41.get_collection(
            m=b"KPZ",
            f_id=collection.ParameterValue(
                # par=bytes.fromhex("0000000200ff02"),
                par=bytes.fromhex("0000600101ff02"),
                value=cdt.OctetString(bytearray(b'M2M_1')).encoding),
            ver=collection.ParameterValue(
                par=bytes.fromhex("0000000201ff02"),
                value=cdt.OctetString(bytearray(b"1.7.3")).encoding
            ))
        print(col)
        ass: collection.AssociationLN = col.get_object("0.0.40.0.3.255")
        for el in tuple(ass.object_list):
            el: collection.ObjectListElement
            if el.logical_name in (cst.LogicalName.from_obis("0.0.40.0.3.255"), cst.LogicalName.from_obis("0.0.1.0.0.255")):
                pass
            else:
                ass.object_list.remove(el)
        col.set_firm_id(value=collection.ParameterValue(b'', cdt.OctetString("00").encoding), force=True)
        xml50.create_type(col)
        print(ass.object_list.encoding.hex())

    def test_get_collection41(self):
        col = Xml41.get_collection(
            m=b"KPZ",
            f_id=collection.ParameterValue(
                # par=bytes.fromhex("0000000200ff02"),
                par=bytes.fromhex("0000600101ff02"),
                value=cdt.OctetString(bytearray(b'M2M_1')).encoding),
            ver=collection.ParameterValue(
                par=bytes.fromhex("0000000201ff02"),
                value=cdt.OctetString(bytearray(b"1.7.3")).encoding
            ))
        print(col)
        col.LDN.set_attr(2, bytearray(b"KPZ00001234567890"))  # need for test
        col2 = col.copy()
        # keep path
        clock_obj = col.get_object("0.0.1.0.0.255")
        clock_obj.set_attr(3, 100)  # change any value for test
        iccid_obj = col.get_object("0.128.25.6.0.255")
        iccid_obj.set_attr(2, "01 02 03 04 05")
        Xml41.keep_data(col)
        # get data
        Xml41.get_data(col2)
        print(col2)

    def test_get_collection50(self):
        col = xml50.get_collection(
            m=b"KPZ",
            f_id=collection.ParameterValue(
                par=bytes.fromhex("0000000200ff02"),
                value=bytes.fromhex("090e5057524d5f4d324d5f315f46345f")),
            ver=collection.ParameterValue(
                par=bytes.fromhex("0000000201ff02"),
                value=cdt.OctetString(bytearray(b"1.7.3")).encoding))
        # col2 = xml50.get_collection(
        #     m=b"KPZ",
        #     f_id=collection.ParameterValue(
        #         par=bytes.fromhex("0000000200ff02"),
        #         value=bytes.fromhex("090e5057524d5f4d324d5f315f46345f")
        #     ),
        #     ver=collection.ParameterValue(
        #         par=bytes.fromhex("0000000201ff02"),
        #         value=cdt.OctetString(bytearray(b"1.7.4")).encoding
        #     )
        # )
        print(col)
        col.LDN.set_attr(2, bytearray(b"KPZ00001234567890"))  # need for test
        col2 = col.copy()
        # col2.LDN.set_attr(2, bytearray(b"KPZ00001234567891"))  # need for test
        # keep path
        clock_obj = col.get_object("0.0.1.0.0.255")
        clock_obj.set_attr(3, 100)  # change any value for test
        iccid_obj = col.get_object("0.128.25.6.0.255")
        iccid_obj.set_attr(2, "01 02 03 04 05")
        xml50.keep_data(col)
        # get data
        xml50.get_data(col2)
        print(col2)

    def test_template(self):
        adapter = xml50
        col = adapter.get_collection(
            m=b"KPZ",
            f_id=serID50_M2M_1,
            ver=server_1_7_3)
        # col2 = adapter.get_collection(
        #     m=b"KPZ",
        #     f_id=serID50_M2M_1,
        #     ver=server_1_7_4)
        clock_obj = col.get_object("0.0.1.0.0.255")
        clock_obj.set_attr(3, 120)
        act_cal = col.get_object("0.0.13.0.0.255")
        act_cal.day_profile_table_passive.append((1, [("11:00", "01 01 01 01 01 01", 1)]))
        adapter.create_template(
            name="template_test1",
            template=collection.Template(
                collections=[
                    col,
                    # col2
                ],
                used={
                    clock_obj.logical_name: {3},
                    act_cal.logical_name: {9}
                }
            ))
        template = adapter.get_template("template_test1")
        print(template)

    def test_get_all_collection(self):
        """try get all collection"""
        for i in Xml41.get_manufactures_container().values():
            for j in i.values():
                for path in j.values():
                    print(path)
                    logger.info(F"find type {path=}")
                    tree = ET.parse(path)
                    col = Xml41.root2collection(tree.getroot(), collection.Collection())
                    print(col)

    def test_get_col_path(self):
        path = Xml3.get_col_path(
            m=b"KPZ",
            f_id=collection.ParameterValue(
                par=bytes.fromhex("0000600102ff02"),
                value=cdt.OctetString(bytearray(b'M2M_3')).encoding
            ),
            ver=collection.ParameterValue(
                par=bytes.fromhex("0000000201ff02"),
                value=cdt.OctetString(bytearray(b"1.4.13+r")).encoding
            )
        )
        print(path)
