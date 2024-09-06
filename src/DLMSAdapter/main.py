from abc import ABC, abstractmethod
import asyncio
from DLMS_SPODES.cosem_interface_classes.collection import (
    Collection,
    FirmwareID,
    FirmwareVersion,
    Template)
from semver import Version as SemVer


type_title: str = "DLMSServerType"
data_title: str = "DLMSServerData"
template_title: str = "DLMSServerTemplate"


class Adapter(ABC):
    """universal adapter for keep/recovery DLMS data"""
    VERSION: SemVer = SemVer(0, 0)
    """reinit current adapter version"""

    @classmethod
    @abstractmethod
    def create_type(cls, col: Collection):
        """not safety of type keeping from collection(source) to destination(file(xml, json,...), sql, etc...). Save all attributes. For types only STATIC save """

    @classmethod
    @abstractmethod
    def keep_data(cls, col: Collection, ass_id: int = 3) -> bool:
        """Save attributes WRITABLE and STATIC if possible. Use LDN as ID"""

    @classmethod
    @abstractmethod
    def get_data(cls, col: Collection):
        """ set attribute values from file by. validation ID's """

    @classmethod
    @abstractmethod
    def get_collection(cls,
                       m: bytes,
                       f_id: FirmwareID,
                       ver: FirmwareVersion) -> Collection:
        """get Collection by m: manufacturer, t: type, ver: version"""

    @classmethod
    @abstractmethod
    def create_template(cls,
                        name: str,
                        template: Template):
        """keep used values to template by collections with <name>"""

    @classmethod
    @abstractmethod
    def get_template(cls, name: str) -> Template:
        """load template by <name>"""


class AdapterException(Exception):
    """"""


