# Project Rules

## Python Environment

### Virtual Environment
- **MUST** use `uv` to create and manage virtual environments
- Python version: **3.13.3**
- Always activate virtual environment before running Python code

### Dependency Management
- Use `uv pip install` to install dependencies
- **MUST** use Tsinghua mirror for faster downloads:
  ```bash
  uv pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <package>
  ```
- For installing from requirements.txt:
  ```bash
  uv pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
  ```

### Running Python Code
- **MUST** run Python code inside the virtual environment
- Before executing any Python scripts, ensure virtual environment is activated:
  ```bash
  # Windows (PowerShell)
  .venv\Scripts\Activate.ps1
  
  # Windows (CMD)
  .venv\Scripts\activate.bat
  ```

### Initial Setup
When setting up the project for the first time:
1. Create virtual environment with uv:
   ```bash
   uv venv --python 3.13.3
   ```
2. Activate the virtual environment
3. Install dependencies:
   ```bash
   uv pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
   ```

### Project Structure
- `tools/` - Standalone Python scripts
- `requirements.txt` - Project dependencies
- `pyproject.toml` - Project configuration
