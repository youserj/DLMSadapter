from abc import ABC, abstractmethod
import logging
from DLMS_SPODES.cosem_interface_classes.collection import (
    Collection, ID,
    ParameterValue,
    Template)
from semver import Version as SemVer


logger = logging.getLogger(__name__)
type_title: str = "DLMSServerType"
data_title: str = "DLMSServerData"
template_title: str = "DLMSServerTemplate"


class Adapter(ABC):
    """universal adapter for keep/recovery DLMS data"""
    VERSION: SemVer = SemVer(0, 0)
    """reinit current adapter version"""

    @classmethod
    @abstractmethod
    def set_collection(cls, col: Collection):
        """not safety of type keeping from collection(source) to destination(file(xml, json,...), sql, etc...). Save all attributes. For types only STATIC save """

    @classmethod
    @abstractmethod
    def get_collection(cls,
                       m: bytes,
                       f_id: ParameterValue,
                       ver: ParameterValue) -> Collection:
        """get Collection by m: manufacturer, t: type, ver: version. AdapterException if not find collection by ID """

    @abstractmethod
    def get_collectionIDs(self) -> list[ID]:
        """return container used CollectionID"""

    @classmethod
    @abstractmethod
    def set_data(cls, col: Collection, ass_id: int = 3) -> bool:
        """Save attributes WRITABLE and STATIC if possible. Use LDN as ID"""

    @classmethod
    @abstractmethod
    def get_data(cls, col: Collection):
        """ set attribute values from file by. validation ID's. AdapterException if not find data by ID"""

    @abstractmethod
    def set_template(self, template: Template):
        """keep used values to template by collections"""

    @classmethod
    @abstractmethod
    def get_template(cls, name: str) -> Template:
        """load template by <name>"""

    @classmethod
    @abstractmethod
    def get_templates(cls) -> list[str]:
        """return all templates name"""


class AdapterException(Exception):
    """"""


class __Gag(Adapter):
    @classmethod
    def set_collection(cls, col: Collection):
        logger.warning(F"{cls.__name__} not support <get_template>")

    @classmethod
    def get_collection(cls, m: bytes, f_id: ParameterValue, ver: ParameterValue) -> Collection:
        raise AdapterException(F"{cls.__name__} not support <get_collection>")

    @classmethod
    def set_data(cls, col: Collection, ass_id: int = 3) -> bool:
        raise AdapterException(F"{cls.__name__} not support <keep_data>")

    @classmethod
    def get_data(cls, col: Collection):
        raise AdapterException(F"{cls.__name__} not support <get_data>")

    def set_template(self, template: Template):
        raise AdapterException(F"{self.__class__.__name__} not support <create_template>")

    @classmethod
    def get_template(cls, name: str) -> Template:
        raise AdapterException(F"{cls.__name__} not support <get_template>")

    @classmethod
    def get_templates(cls) -> list[str]:
        raise AdapterException(F"{cls.__name__} not have <templates>")

    def get_collectionIDs(self) -> list[ID]:
        raise AdapterException(F"{self.__name__} not have <manufacturers>")


gag = __Gag()
