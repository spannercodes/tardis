from .model import *

from sqlmodel import SQLModel, Session, select, func, or_
from fastapi import Depends
from typing import Annotated
from datetime import datetime

def register_primitives(tardis):
    tardis.register_datatype("tardis:float", float)
    tardis.register_datatype("tardis:integer", int)
    tardis.register_datatype("tardis:set", set)
    tardis.register_datatype("tardis:list", list)

    # TODO: this could be merged with the above
    tardis.register_value_getter("tardis:numeric:float", "tardis:numeric:value")
    tardis.register_value_getter("tardis:numeric:integer", "tardis:numeric:value")
    tardis.register_value_getter("tardis:set", "tardis:set:value")
    tardis.register_value_getter("tardis:list", "tardis:list:value")

    @tardis.getter(["tardis:integer", "tardis:float"], "tardis:numeric:value")
    async def numeric_value(
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        at: datetime = None) -> str:

        starting_value_update = db.exec(select(FieldUpdate).where(
            FieldUpdate.setter == "value",
            FieldUpdate.subject_type == subject_type,
            FieldUpdate.subject_identifier == subject_identifier,
            (FieldUpdate.updated_at <= at if at is not None else True),
        ).order_by(FieldUpdate.updated_at.desc()).limit(1)).first()

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
        at: datetime = None) -> str:

        starting_value_update = db.exec(select(FieldUpdate).where(
            FieldUpdate.setter == "value",
            FieldUpdate.subject_type == subject_type,
            FieldUpdate.subject_identifier == subject_identifier,
            (FieldUpdate.updated_at <= at if at is not None else True),
        ).order_by(FieldUpdate.updated_at.desc()).limit(1)).first()

        value = set(starting_value_update.body) if starting_value_update is not None else set()

        updates = db.exec(select(FieldUpdate.setter, FieldUpdate.body).where(
            FieldUpdate.field == field,
            or_(FieldUpdate.setter == "tardis:set:put", FieldUpdate.setter == "tardis:set:remove"),
            FieldUpdate.subject_type == subject_type,
            FieldUpdate.subject_identifier == subject_identifier,
            (FieldUpdate.updated_at >= starting_value_update.updated_at if starting_value_update is not None else True),
            (FieldUpdate.updated_at <= at if at is not None else True),
        ).order_by(FieldUpdate.updated_at.desc())).all()

        for setter,item in updates:
            if setter == "tardis:set:put":
                value.add(item)
            if setter == "tardis:set:remove":
                value.difference_update([item])

        return value

    @tardis.getter(["tardis:list"], "tardis:list:value")
    async def list_value(
        db: Annotated[Session, Depends(tardis.db)],
        field: str, subject_type: str, subject_identifier: str,
        at: datetime = None) -> str:

        starting_value_update = db.exec(select(FieldUpdate).where(
            FieldUpdate.setter == "value",
            FieldUpdate.subject_type == subject_type,
            FieldUpdate.subject_identifier == subject_identifier,
            (FieldUpdate.updated_at <= at if at is not None else True),
        ).order_by(FieldUpdate.updated_at.desc()).limit(1)).first()

        print(starting_value_update)

        value: list = list(starting_value_update.body) if starting_value_update is not None else []

        updates = db.exec(select(FieldUpdate.setter, FieldUpdate.body, FieldUpdate.params).where(
            FieldUpdate.field == field,
            or_(FieldUpdate.setter == "tardis:list:append", FieldUpdate.setter == "tardis:list:remove", FieldUpdate.setter == "tardis:list:insert"),
            FieldUpdate.subject_type == subject_type,
            FieldUpdate.subject_identifier == subject_identifier,
            (FieldUpdate.updated_at >= starting_value_update.updated_at if starting_value_update is not None else True),
            (FieldUpdate.updated_at <= at if at is not None else True),
        ).order_by(FieldUpdate.updated_at.desc())).all()

        for setter,item,params in updates:
            print(setter, item, params)
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