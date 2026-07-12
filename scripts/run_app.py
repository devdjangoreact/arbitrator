#!/usr/bin/env python3
import sys
import os
import subprocess
from pathlib import Path
import uvicorn

# Ensure the root directory is in the Python path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))
sys.path.insert(0, str(root_dir)) # Add root so 'main' can be resolved

from arbitrator.config.settings import Settings

def main():
    settings = Settings()
    
    if settings.use_react_frontend:
        print("React frontend enabled. Starting build process...")
        react_dir = root_dir / "src" / "arbitrator" / "presentation" / "react-ui"
        
        print("Running pnpm install...")
        install_result = subprocess.run(["pnpm", "install"], cwd=str(react_dir), shell=True)
        if install_result.returncode != 0:
            print("Failed to install React dependencies. Exiting.", file=sys.stderr)
            sys.exit(install_result.returncode)
            
        print("Running pnpm build...")
        build_result = subprocess.run(["pnpm", "build"], cwd=str(react_dir), shell=True)
        if build_result.returncode != 0:
            print("Failed to build React frontend. Exiting.", file=sys.stderr)
            sys.exit(build_result.returncode)
            
        print("React frontend build complete.")
    else:
        print("Legacy vanilla JS frontend enabled. Skipping build process.")
        
    print("Starting FastAPI server...")
    # Change working directory to root so uvicorn can find 'main:app'
    os.chdir(str(root_dir))
    uvicorn.run("main:app", host=settings.fastapi_host, port=settings.fastapi_port, reload=settings.fastapi_reload)

if __name__ == "__main__":
    main()
