The migration in this directory was generated with the following commands:

```shell
docker-compose -f ../docker-compose.yaml up
env TEST_DATABASE_URL=postgresql://example@localhost/example \
    TEST_DATABASE_PASSWORD=INSECURE \
    PYTHONPATH=$(pwd)/../../../.. \
    alembic revision --autogenerate -m "V1 schema"
```

When regenerating them, also see `../v2/README.md` in case you want to regenerate that migration as well.
