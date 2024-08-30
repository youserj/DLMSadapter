import unittest
from DLMS_SPODES.cosem_interface_classes import collection
from DLMS_SPODES.types import cdt, cst
from src.DLMSAdapter import Xml40
from src.DLMSAdapter.xml import get_manufactures_container
import logging


adapter = Xml40()
logger = logging.getLogger(__name__)
logger.level = logging.INFO


class TestType(unittest.TestCase):
    def test_create_adapter(self):
        adapter_ = Xml40()

    def test_create_type(self):
        col = collection.Collection(
            man=b'XXX',
            s_id=collection.ServerId(b'1234567', cdt.OctetString(bytearray(b'M2M-1'))),
            s_ver=collection.ServerVersion(b'1234560', cdt.OctetString(bytearray(b'1.4.2'))))
        print(col)
        col.LDN.set_attr(2, bytearray(b'XXX0000000001234'))
        adapter.create_type(col)

    def test_get_man(self):
        c = get_manufactures_container()
        print(c)

    def test_get_collection(self):
        col = adapter.get_collection(
            m=b"KPZ",
            sid=collection.ServerId(
                par=bytes.fromhex("0000600102ff02"),
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
        adapter.keep_data(col)
        # get data
        adapter.get_data(col2)
        print(col2)

    def test_template(self):
        col = adapter.get_collection(
            m=b"KPZ",
            sid=collection.ServerId(
                par=bytes.fromhex("0000600102ff02"),
                value=cdt.OctetString(bytearray(b'M2M_3'))),
            ver=collection.ServerVersion(
                par=bytes.fromhex("0000000201ff02"),
                value=cdt.OctetString(bytearray(b"1.4.15"))))
        col2 = adapter.get_collection(
            m=b"102",
            sid=collection.ServerId(
                par=bytes.fromhex("0000600102ff02"),
                value=cdt.OctetString(bytearray(b'M2M_3'))),
            ver=collection.ServerVersion(
                par=bytes.fromhex("0000000201ff02"),
                value=cdt.OctetString(bytearray(b"1.3.30"))))
        clock_obj = col.get_object("0.0.1.0.0.255")
        clock_obj.set_attr(3, 120)
        act_cal = col.get_object("0.0.13.0.0.255")
        act_cal.day_profile_table_passive.append((1, [("11:00", "01 01 01 01 01 01", 1)]))
        used = {
            clock_obj.logical_name: {3},
            act_cal.logical_name: {9}
        }
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