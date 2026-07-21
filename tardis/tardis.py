from .primitives import register_primitives

from sqlmodel import SQLModel, Session, create_engine
from typing import Union
from fastapi import FastAPI, APIRouter, Request, Response, Depends, HTTPException
import uvicorn

class TARDIS:
    def __init__(self, database_uri: str):
        self.router = APIRouter()
        self.registered_datatypes = {}
        self.registered_value_getters = {}
        self.registered_fields = {}
        self.registered_getters = {}
        self.registered_setters = {}

        self.fastapi = FastAPI()
        self.fastapi.include_router(self.router)
        self.fastapi.middleware("http")(self._field_value_getter)
        self.engine = create_engine(database_uri, echo=True)
        SQLModel.metadata.create_all(self.engine)

        register_primitives(self)
    
    def register_datatype(self, identifier: str, model):
        self.registered_datatypes[identifier] = model
    
    def register_value_getter(self, datatype: str, getter_identifier: str):
        self.registered_value_getters[datatype] = getter_identifier
    
    def register_field(self, identifier: str, datatype: str):
        self.registered_fields[identifier] = datatype
    
    def register_getter(self, datatypes: list[str], identifier: str, getter, **kwargs):
        response_types = []
        for datatype in datatypes:
            dt = self.registered_datatypes.get(datatype)
            if dt is None:
                raise ValueError(f"datatype not registered: {datatype}")
            response_types.append(dt)
        self.router.get(f"/{{field}}/{identifier}/{{subject_type}}/{{subject_identifier}}", response_model=Union[*response_types], dependencies=[Depends(self._validate_field)])(getter)
    def getter(self, datatypes: list[str], identifier: str, **kwargs):
        def wrapper(getter):
            self.register_getter(datatypes, identifier, getter, **kwargs)
        return wrapper
    
    async def _field_value_getter(self, request: Request, call_next):
        s = request.scope["path"].split('/')[1:]
        if len(s) == 4 and s[1] == "value":
            field,_,subject_type,subject_identifier = s
            if field is not None:
                datatype = self.registered_fields.get(field)
                if datatype is None:
                    raise HTTPException(status_code=404, detail=f"Field {field} is not registered in this store")
                getter = self.registered_value_getters.get(datatype)
                if getter is None:
                    raise HTTPException(status_code=404, detail=f"A value getter has not been defined for the datatype {datatype}")
                request.scope["path"] = f"/{field}/{getter}/{subject_type}/{subject_identifier}"
        return await call_next(request)
    
    async def _validate_field(self, field: str):
        if field not in self.registered_fields:
            raise HTTPException(status_code=404, detail=f"Field {field} is not registered in this store")
    
    def db(self) -> Session:
        with Session(self.engine) as s:
            yield s
    
    def serve(self, host="0.0.0.0", port=1963):
        uvicorn.run(self.fastapi, host=host, port=port)
