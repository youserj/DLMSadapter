from .main import (
    Adapter, AdapterException,
    Collection, ParameterValue, Template,
)
from .xml_ import (
    Xml50, Xml40, Xml41, Xml3, xml50
)
from DLMS_SPODES.config_parser import get_values


CREATE_TYPE = "create_type"
GET_COLLECTION = "get_collection"
KEEP_DATA = "keep_data"
GET_DATA = "get_data"
CREATE_TEMPLATE = "create_template"
GET_TEMPLATE = "get_template"


_container: dict[str, list[str]] = {
    CREATE_TYPE: ["Xml50"],
    GET_COLLECTION: ["Xml50"],
    KEEP_DATA: ["Xml50"],
    GET_DATA: ["Xml50"],
    CREATE_TEMPLATE: ["Xml50"],
    GET_TEMPLATE: ["Xml50"]
}
"""default parameters from toml"""
_adapters: dict[str, list[Adapter]] = {
    CREATE_TYPE: list(),
    GET_COLLECTION: list(),
    KEEP_DATA: list(),
    GET_DATA: list(),
    CREATE_TEMPLATE: list(),
    GET_TEMPLATE: list()
}

"""Pool parameters"""

if toml_val := get_values("DLMSAdapter", "Pool"):
    _container.update(toml_val)
for n, c in _container.items():
    for val in c:
        if isinstance((adapter := vars().get(val)), Adapter):
            _adapters[n].append(adapter)

del _container


class Pool(Adapter):
    """"""

    @classmethod
    def create_type(cls, col: Collection):
        for adp in _adapters[CREATE_TYPE]:
            adp.create_type(col)

    @classmethod
    def get_collection(cls, m: bytes, f_id: ParameterValue, ver: ParameterValue) -> Collection:
        ret = None
        for adp in _adapters[GET_COLLECTION]:
            try:
                return adp.get_collection(m, f_id, ver)
            except AdapterException as e:
                ret = e
        else:
            raise ret

    @classmethod
    def keep_data(cls, col: Collection, ass_id: int = 3) -> bool:
        ret = False
        for adp in _adapters[KEEP_DATA]:
            if tmp := adp.keep_data(col, ass_id):
                ret = tmp
        return ret

    @classmethod
    def get_data(cls, col: Collection):
        ret = None
        for adp in _adapters[GET_DATA]:
            try:
                adp.get_data(col)
                break
            except AdapterException as e:
                ret = e
        else:
            raise ret

    @classmethod
    def create_template(cls, name: str, template: Template):
        pass

    @classmethod
    def get_template(cls, name: str) -> Template:
        pass
