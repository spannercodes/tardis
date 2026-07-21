from tardis import TARDIS, FieldUpdate

from datetime import timedelta
from random import choice, randint, uniform
from sqlmodel import Session
from uuid import uuid4
from datetime import datetime, timedelta

if __name__ == "__main__":
    tardis = TARDIS("sqlite:///tardis_example.sqlite")

    with Session(tardis.engine) as db:
        for _ in range(100):
            db.add(FieldUpdate(
                id=uuid4(),
                event=uuid4(),
                field="example:integer",
                setter="tardis:numeric:delta",
                subject_type="example:person",
                subject_identifier=choice(["hannah", "alice", "bob"]),
                body=randint(1,5),
                updated_at=datetime.now()+timedelta(hours=randint(-256,0))
            ))
            db.add(FieldUpdate(
                id=uuid4(),
                event=uuid4(),
                field="example:float",
                setter="tardis:numeric:delta",
                subject_type="example:person",
                subject_identifier=choice(["hannah", "alice", "bob"]),
                body=uniform(1,5),
                updated_at=datetime.now()+timedelta(hours=randint(-256,0))
            ))
            db.add(FieldUpdate(
                id=uuid4(),
                event=uuid4(),
                field="example:set",
                setter=choice(["tardis:set:put", "tardis:set:remove"]),
                subject_type="example:person",
                subject_identifier=choice(["hannah", "alice", "bob"]),
                body=choice(list("abcdefghijklmnopqrstuvwxyz")),
                updated_at=datetime.now()+timedelta(hours=randint(-256,0))
            ))

        db.commit()