# Project-local Python environment

PetLink uses the local `.venv` directory. It does not modify the Windows
system `PATH` or install project packages globally.

In PowerShell, from the project folder:

```powershell
.\.venv\Scripts\Activate.ps1
python --version
```

To leave the environment:

```powershell
deactivate
```

The project and its PySide6, SQLAlchemy and Alembic dependencies are installed in
`.venv`. Run without activation using:

```powershell
.\.venv\Scripts\python.exe -m petlink
```

To update the project dependencies, the global pip can target this environment
directly even when `.venv` has no pip of its own:

```powershell
python -m pip --python .venv\Scripts\python.exe install -e .
```

## One-click launch

Double-click `run_petlink.bat`. It selects the project-local interpreter and
starts PetLink without requiring manual environment activation first.
