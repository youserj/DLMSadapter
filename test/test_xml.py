import unittest
from DLMS_SPODES.cosem_interface_classes import collection, overview
from DLMS_SPODES.types import cdt, cst
from src.DLMSAdapter.xml_ import Xml41, Xml50, Xml40, Xml3, ET
import logging

server_1_4_15 = collection.ServerVersion(
        par=bytes.fromhex("0000000201ff02"),
        value=cdt.OctetString(bytearray(b"1.4.15")))
serID_M2M_1 = collection.ServerId(
        par=bytes.fromhex("0000600101ff02"),
        value=cdt.OctetString(bytearray(b'M2M_1')))
serID_M2M_3 = collection.ServerId(
        par=bytes.fromhex("0000600101ff02"),
        value=cdt.OctetString(bytearray(b'M2M_3')))


logger = logging.getLogger(__name__)
logger.level = logging.INFO


class TestType(unittest.TestCase):
    def test_create_adapter(self):
        adapter_ = Xml41()

    def test_create_type(self):
        col = collection.Collection(
            man=b'XXX',
            s_id=collection.ServerId(b'1234567', cdt.OctetString(bytearray(b'M2M-1'))),
            s_ver=collection.ServerVersion(b'1234560', cdt.OctetString(bytearray(b'1.4.2'))))
        print(col)
        clock_obj = col.add(
            overview.ClassID.CLOCK,
            overview.Version.V0,
            cst.LogicalName.from_obis("0.0.1.0.0.255"))
        clock_obj.set_attr(3, 120)
        # col.LDN.set_attr(2, bytearray(b'XXX0000000001234'))
        Xml41.create_type(col)
        Xml50.create_type(col)

    def test_get_man(self):
        c = Xml3.get_manufactures_container()
        print(c)

    def test_get_collection(self):
        col = Xml41.get_collection(
            m=b"KPZ",
            sid=collection.ServerId(
                par=bytes.fromhex("0000600101ff02"),
                value=cdt.OctetString(bytearray(b'M2M_1'))),
            ver=collection.ServerVersion(
                par=bytes.fromhex("0000000201ff02"),
                value=cdt.OctetString(bytearray(b"1.7.3"))))
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

    def test_template(self):
        adapter = Xml41
        col = adapter.get_collection(
            m=b"KPZ",
            sid=serID_M2M_3,
            ver=server_1_4_15)
        col2 = adapter.get_collection(
            m=b"102",
            sid=serID_M2M_3,
            ver=collection.ServerVersion(
                par=bytes.fromhex("0000000201ff02"),
                value=cdt.OctetString(bytearray(b"1.3.30"))))
        clock_obj = col.get_object("0.0.1.0.0.255")
        clock_obj.set_attr(3, 120)
        act_cal = col.get_object("0.0.13.0.0.255")
        act_cal.day_profile_table_passive.append((1, [("11:00", "01 01 01 01 01 01", 1)]))
        adapter.create_template(
            name="template_test1",
            template=collection.Template(
                collections=[col, col2],
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
            sid=collection.ServerId(
                par=bytes.fromhex("0000600102ff02"),
                value=cdt.OctetString(bytearray(b'M2M_3'))
            ),
            ver=collection.ServerVersion(
                par=bytes.fromhex("0000000201ff02"),
                value=cdt.OctetString(bytearray(b"1.4.13+r"))
            )
        )
        print(path)
