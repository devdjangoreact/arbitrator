# Contracts: React Frontend Architecture

*Note: This architectural phase does not introduce new API contracts. It solely modifies how static assets are served.*

## Internal Application Contract (FastAPI Static Mounting)

The contract between the frontend build process and the FastAPI backend relies on the file system structure:

- **Legacy UI Path**: `src/arbitrator/presentation/static`
- **Modern UI Path**: `src/arbitrator/presentation/react-ui/dist`
  - The backend expects the Vite build process to output its production-ready assets to this specific `dist` folder.
  - The backend expects an `index.html` file to exist at the root of the active static directory.
