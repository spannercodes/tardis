from __future__ import nested_scopes
from .model import *

from sqlmodel import SQLModel, Session, select, func, or_
from fastapi import Depends, Request
from typing import Annotated, Any
from datetime import datetime, timezone
from uuid import UUID, uuid4
import numpy as np
from urllib.parse import parse_qs

def get_starting_value_update(db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        at: datetime = None) -> FieldUpdate | None:
    return  db.exec(select(FieldUpdate).where(
                FieldUpdate.field == field,
                FieldUpdate.setter == "value",
                FieldUpdate.subject_type == subject_type,
                FieldUpdate.subject_identifier == subject_identifier,
                (FieldUpdate.updated_at <= at if at is not None else True),
            ).order_by(FieldUpdate.updated_at.desc()).limit(1)).first()

def get_updates(db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        starting_value_update: FieldUpdate | None,
        setters: list[str],
        at: datetime = None) -> list[FieldUpdate]:

    setter_matcher = or_(*[FieldUpdate.setter == setter for setter in setters])
    return  db.exec(select(FieldUpdate.setter, FieldUpdate.body, FieldUpdate.params).where(
                FieldUpdate.field == field,
                setter_matcher,
                FieldUpdate.subject_type == subject_type,
                FieldUpdate.subject_identifier == subject_identifier,
                (FieldUpdate.updated_at >= starting_value_update.updated_at if starting_value_update is not None else True),
                (FieldUpdate.updated_at <= at if at is not None else True),
            ).order_by(FieldUpdate.updated_at.asc())).all()

async def generic_setter(
        setter: str,
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        request: Request, event: str = None):

    body = await request.json()

    if event is None:
        event = uuid4()
    else:
        event = UUID(event)

    params = dict(request.query_params)
    if "event" in params:
        del params["event"]

    update = FieldUpdate(
        id=uuid4(),
        event=event,
        field=field,
        setter=setter,
        subject_type=subject_type,
        subject_identifier=subject_identifier,
        body=body,
        updated_at=datetime.now(timezone.utc), # TODO: this should maybe be taken from what the client says, else you might have one event with several update times
        params=params,
    )

    db.add(update)
    db.commit()

def register_primitives(tardis):
    tardis.register_datatype("tardis:float", float)
    tardis.register_datatype("tardis:integer", int)
    tardis.register_datatype("tardis:set", set)
    tardis.register_datatype("tardis:list", list)
    tardis.register_datatype("tardis:string", str)

    @tardis.getter(["tardis:string"], "tardis:simple:value")
    async def simple_value(
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        at: datetime = None,
        default=None) -> Any:
        starting_value_update = get_starting_value_update(db, field, subject_type, subject_identifier, at)
        starting_value = starting_value_update.body if starting_value_update is not None else default
        return starting_value

    @tardis.getter(["tardis:integer", "tardis:float"], "tardis:numeric:value")
    async def numeric_value(
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        at: datetime = None) -> int | float:

        starting_value_update = get_starting_value_update(db, field, subject_type, subject_identifier, at)

        starting_value = starting_value_update.body if starting_value_update is not None else 0

        delta = db.exec(select(func.sum(FieldUpdate.body)).where(
            FieldUpdate.field == field,
            FieldUpdate.setter == "tardis:numeric:delta",
            FieldUpdate.subject_type == subject_type,
            FieldUpdate.subject_identifier == subject_identifier,
            (FieldUpdate.updated_at >= starting_value_update.updated_at if starting_value_update is not None else True),
            (FieldUpdate.updated_at <= at if at is not None else True),
        )).first() or 0

        return starting_value + delta

    @tardis.getter(["tardis:set"], "tardis:set:value")
    async def set_value(
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        at: datetime = None) -> set:

        starting_value_update = get_starting_value_update(db, field, subject_type, subject_identifier, at)

        value = set(starting_value_update.body) if starting_value_update is not None else set()

        setters = ["tardis:set:put", "tardis:set:remove"]

        updates = get_updates(db, field, subject_type, subject_identifier, starting_value_update, setters, at)

        for setter,item,params in updates:
            if setter == "tardis:set:put":
                value.add(item)
            if setter == "tardis:set:remove":
                value.difference_update([item])

        return value

    @tardis.getter(["tardis:list"], "tardis:list:value")
    async def list_value(
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        at: datetime = None) -> list:

        starting_value_update = get_starting_value_update(db, field, subject_type, subject_identifier, at)

        value: list = list(starting_value_update.body) if starting_value_update is not None else []

        setters = ["tardis:list:append", "tardis:list:remove", "tardis:list:insert"]

        updates = get_updates(db, field, subject_type, subject_identifier, starting_value_update, setters, at)

        for setter,item,params in updates:
            if setter == "tardis:list:append":
                value.append(item)
            if setter == "tardis:list:remove":
                try:
                    value.remove(item)
                except ValueError:
                    pass
                    # print(f"Failed to remove item from list (length {len(value)})). Probably a reverted event without a value being set. Horrors!")
            if setter == "tardis:list:insert":
                index = params.get("index")
                if index is not None:
                    try:
                        value.insert(int(params.get("index")), item)
                    except:
                        pass
                        # print(f"Failed to insert to an array at index {index}. Probably a reverted event without a value being set. Horrors!")

        return value

    @tardis.getter(["tardis:list", "tardis:set"], "tardis:collection:average", response_model=float)
    async def collection_avg(
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        at: datetime = None) -> float:

        datatype = tardis.registered_fields.get(field)
        value_getter = tardis.registered_value_getters.get(datatype)
        if value_getter is None:
            raise ValueError(f"Value getter is not set for datatype {datatype}")
        
        _,getter = value_getter

        value = await getter(db, field, subject_type, subject_identifier, at)

        return float(np.average(value))
    
    @tardis.setter(
        ["tardis:numeric:float", "tardis:numeric:integer", "tardis:set", "tardis:list", "tardis:string"],
        "tardis:simple:value"
        )
    async def simple_value(
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        request: Request, event: str = None):

        return await generic_setter("value", db, field, subject_type, subject_identifier, request, event)

    @tardis.setter(["tardis:list"], "tardis:list:append")
    async def list_append(
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        request: Request, event: str = None):

        return await generic_setter("tardis:list:append", db, field, subject_type, subject_identifier, request, event)

    @tardis.setter(["tardis:integer", "tardis:float"], "tardis:numeric:delta")
    async def numeric_delta(
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        request: Request, event: str = None):

        return await generic_setter("tardis:numeric:delta", db, field, subject_type, subject_identifier, request, event)
    
    tardis.register_value_modifiers("tardis:numeric:float", "tardis:numeric:value", "tardis:simple:value")
    tardis.register_value_modifiers("tardis:numeric:integer", "tardis:numeric:value", "tardis:simple:value")
    tardis.register_value_modifiers("tardis:set", "tardis:set:value", "tardis:simple:value")
    tardis.register_value_modifiers("tardis:list", "tardis:list:value", "tardis:simple:value")
    tardis.register_value_modifiers("tardis:string", "tardis:simple:value", "tardis:simple:value")
