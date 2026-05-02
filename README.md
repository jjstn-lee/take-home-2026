# Channel3 - Product Hydration & E-Commerce Frontend

## Installation & Setup

### 1. Backend Setup

**Install Python Dependencies:**

```bash
cd /path/to/backend
uv sync  # Uses pyproject.toml to install all dependencies
```

**Set Environment Variables:**

```bash
# Open/create .env file at root and add key
OPEN_ROUTER_API_KEY="sk-..."
```

**Start the Backend Server:**

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

- API will be available at `http://0.0.0.0:8000`
- Swagger docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 2. Frontend Setup

In a **separate terminal**, navigate to the frontend directory:

```bash
cd /path/to/frontend
npm install  # Install Node dependencies
```

**Start the Frontend Dev Server:**

```bash
npm run dev
```

- Frontend will be available at `http://localhost:5173` (or next available port)
- To avoid configuration issues, ensure that frontend is available on ports 5173-5175. 
- Open in browser to view the application

## System Design

### Backend
This system uses 2-3 synchronous LLM calls per product. To scale this system up from 5 products to 50 million products, we would need Kafka or some other message queue. This would allow the program to asynchronously work through the HTML files at whatever rate it can handle while preventing things like blocking, timing out, or losing data under load. I understand that Channel3 uses Kafka in production. In addition, storing the hydrated Products in memory is fine for 5 products, but will break under 50 million. We would also need to use a relational database (i.e, PostgreSQL), and we could store raw HTML files in an object store like S3. The last major change would be to create a cache. Currently, the system does one LLM pass per product request. But this could be reduced if we kept high-traffic products in caches like Redis. 


### Frontend

The system's current API is very unfriendly to agents. I would implement more agent-friendly endpoints, like a `/search` endpoint that accepts a description and returns a list of products. It's my understanding that Channel3 has a graph representation of products, which I think would be very helpful if we were to scale up this system and optimize for agent use over human use. Similar to how I embedded the Google Product Taxonomy categories, creating product embeddings would be helpful to developers so that they could implement their own search engines.