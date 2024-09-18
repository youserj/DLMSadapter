import unittest
from src.DLMSAdapter.pool import Pool
# from DLMS_SPODES.cosem_interface_classes import collection, overview
# from DLMS_SPODES.types import cdt, cst
# from src.DLMSAdapter.xml_ import Xml41, Xml40, Xml3, ET, Xml50
# import logging


class TestType(unittest.TestCase):
    def test_init_pool(self):
        Pool()

