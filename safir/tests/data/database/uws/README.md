The migration in this directory was generated with the following commands:

```shell
docker-compose -f ../docker-compose.yaml up
env TEST_DATABASE_URL=postgresql://example@localhost/example \
    TEST_DATABASE_PASSWORD=INSECURE \
    PYTHONPATH=$(pwd)/../../../.. \
    alembic revision --autogenerate -m "UWS schema"
```
