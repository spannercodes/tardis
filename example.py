from tardis import TARDIS

tardis = TARDIS("sqlite:///tardis_example.sqlite")

tardis.register_field("example:integer", "tardis:numeric:integer")
tardis.register_field("example:float",   "tardis:numeric:float")
tardis.register_field("example:set",     "tardis:set")
tardis.register_field("example:list",    "tardis:list")

if __name__ == "__main__":
    tardis.serve()

    """
    Now try some HTTP requests!

    GET /example:integer/value/example:person/hannah
    GET /example:float/tardis:numeric:value/example:person/alice
    GET /example:set/value/example:person/bob?at=1783900800
    """