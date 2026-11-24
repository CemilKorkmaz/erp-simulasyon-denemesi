import PyInstaller.__main__

PyInstaller.__main__.run([
    "factory_server/main.py",
    "--name=FactoryERP",
    "--onefile",
    "--windowed",
    "--add-data=factory_server/frontend;factory_server/frontend",
    "--collect-all=fastapi",
    "--collect-all=sqlalchemy",
    "--collect-all=pymodbus",
    "--collect-all=asyncua",
])
