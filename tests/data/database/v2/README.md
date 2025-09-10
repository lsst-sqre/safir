To generate the migration in this directory, first follow the instructions in the `../v1/README.md` file.
In the `../v1` directory, run:

```shell
env TEST_DATABASE_URL=postgresql://example@localhost/example \
    TEST_DATABASE_PASSWORD=INSECURE \
    PYTHONPATH=$(pwd)/../../../.. \
    alembic upgrade head
```

Copy the contents of the `../v1/alembic/versions` directory to an `alembic/versions` subdirectory of this directory.
Then, with the same running database still with the v1 schema installed, run the following command in this directory:

```shell
env TEST_DATABASE_URL=postgresql://example@localhost/example \
    TEST_DATABASE_PASSWORD=INSECURE \
    PYTHONPATH=$(pwd)/../../../.. \
    alembic revision --autogenerate -m "V2 schema"
```
