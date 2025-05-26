# Procfile for multi-process deployment
web: uvicorn adapters.api.main:app --host=0.0.0.0 --port $PORT
bot: python bot_runner.py
checker: python checker_runner.py
