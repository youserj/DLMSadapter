from abc import ABC, abstractmethod
from DLMS_SPODES.cosem_interface_classes.collection import Collection, ServerId, ServerVersion, Template
from DLMS_SPODES.version import AppVersion as SemVer


type_title: str = "DLMSServerType"
data_title: str = "DLMSServerData"
template_title: str = "DLMSServerTemplate"


class Adapter(ABC):
    """universal adapter for keep/recovery DLMS data"""

    @classmethod
    @abstractmethod
    def get_version(cls) -> SemVer:
        """:return current adapter version"""

    @abstractmethod
    def create_type(self, col: Collection):
        """keep type from collection(source) to destination(file(xml, json,...), sql, etc...). Save all attributes. For types only STATIC save """

    @abstractmethod
    def keep_data(self, col: Collection, ass_id: int = 3) -> bool:
        """Save attributes WRITABLE and STATIC if possible. Use LDN as ID"""

    @abstractmethod
    def get_data(self, col: Collection):
        """ set attribute values from file by. validation ID's """

    @abstractmethod
    def get_collection(self,
                       m: bytes,
                       sid: ServerId,
                       ver: ServerVersion) -> Collection:
        """get Collection by m: manufacturer, t: type, ver: version"""

    @abstractmethod
    def create_template(self,
                        name: str,
                        template: Template):
        """keep used values to template by collections with <name>"""

    @abstractmethod
    def get_template(self, name: str) -> Template:
        """load template by <name>"""


class AdapterException(Exception):
    """"""


