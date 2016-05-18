from flask import Flask
from flask.ext.cors import CORS
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.script import Manager
from flask.ext.migrate import Migrate, MigrateCommand


# Create app instance
app = Flask(__name__, instance_relative_config=True)
CORS(app)

# Load default config
app.config.from_object('config')

# Patch config with instance values
app.config.from_pyfile('config.py')

# Init database extension
app_db = SQLAlchemy(app)

# Init manager and register commands
manager = Manager(app)
manager.add_command('db', MigrateCommand)

# Import engine manager here to avoid circular imports
from ais.engine.manage import manager as engine_manager
manager.add_command('engine', engine_manager)

# Init migration extension
migrate = Migrate(app, app_db)
