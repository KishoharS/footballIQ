# DEPLOYMENT GUIDE

This guide covers deploying FootballIQ to production environments.

## Prerequisites

- Docker & Docker Compose (for containerized deployment)
- Python 3.13+ (for local development)
- GROQ API Key ([get one here](https://console.groq.com))

---

## LOCAL DEVELOPMENT

### 1. Setup Environment

```bash
# Clone the repo
cd rag_qa_football

# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure .env
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 2. Run Data Ingestion

```bash
# Run the ingest notebook to populate ChromaDB
jupyter notebook ingest.ipynb

# Or use the command line
python -c "from ingest import *"  # If converted to .py
```

### 3. Run Development Server

```bash
# Fast reload with uvicorn
uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Or using the api directly
python api.py
```

Access the API at:
- **API**: `http://localhost:8000`
- **Docs**: `http://localhost:8000/docs`
- **Health**: `http://localhost:8000/health`

---

## DOCKER DEPLOYMENT

### 1. Build and Run Locally

```bash
# Build the image
docker build -t footballiq:latest .

# Run with environment variables
docker run -p 8000:8000 \
  -e GROQ_API_KEY=$GROQ_API_KEY \
  -v $(pwd)/chroma_db:/app/chroma_db \
  footballiq:latest
```

### 2. Using Docker Compose (Recommended)

```bash
# Copy .env and configure
cp .env.example .env
# Edit .env with your GROQ_API_KEY

# Start the application
docker-compose up -d

# View logs
docker-compose logs -f footballiq

# Stop the application
docker-compose down
```

### 3. Verify Health

```bash
# Check health
curl http://localhost:8000/health

# Expected response:
# {
#   "status": "healthy",
#   "ready": true,
#   "timestamp": 1234567890.12
# }
```

---

## CLOUD DEPLOYMENT

### AWS ECS / Fargate

```bash
# 1. Push image to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

docker tag footballiq:latest <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/footballiq:latest

docker push <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/footballiq:latest

# 2. Create ECS task definition (task-def.json)
# 3. Create ECS service with load balancer
```

### Google Cloud Run

```bash
# Configure gcloud
gcloud config set project PROJECT_ID

# Build and push to GCR
gcloud builds submit --tag gcr.io/PROJECT_ID/footballiq

# Deploy to Cloud Run
gcloud run deploy footballiq \
  --image gcr.io/PROJECT_ID/footballiq \
  --platform managed \
  --region us-central1 \
  --set-env-vars GROQ_API_KEY=$GROQ_API_KEY \
  --allow-unauthenticated \
  --timeout 300
```

### Heroku

```bash
# Login and create app
heroku login
heroku create footballiq-app

# Set environment variables
heroku config:set GROQ_API_KEY=$GROQ_API_KEY --app footballiq-app

# Deploy
git push heroku main

# View logs
heroku logs --tail --app footballiq-app
```

---

## KUBERNETES DEPLOYMENT

### 1. Create ConfigMap and Secrets

```yaml
# config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: footballiq-config
data:
  HOST: "0.0.0.0"
  PORT: "8000"
  CHROMA_DB_PATH: "/data/chroma_db"
  ALLOWED_ORIGINS: "https://yourdomain.com"

---
apiVersion: v1
kind: Secret
metadata:
  name: footballiq-secrets
type: Opaque
stringData:
  GROQ_API_KEY: "your-api-key"
```

### 2. Create Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: footballiq
spec:
  replicas: 3
  selector:
    matchLabels:
      app: footballiq
  template:
    metadata:
      labels:
        app: footballiq
    spec:
      containers:
      - name: footballiq
        image: your-registry/footballiq:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: footballiq-config
        - secretRef:
            name: footballiq-secrets
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 40
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 5
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        volumeMounts:
        - name: chroma-storage
          mountPath: /data/chroma_db
      volumes:
      - name: chroma-storage
        persistentVolumeClaim:
          claimName: footballiq-pvc
```

### 3. Create Service

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: footballiq-service
spec:
  selector:
    app: footballiq
  type: LoadBalancer
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
```

### 4. Deploy

```bash
kubectl apply -f config.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Monitor
kubectl get pods
kubectl logs -f deployment/footballiq
```

---

## PRODUCTION CONSIDERATIONS

### 1. Environment Variables

Always use `.env` files or environment management tools:

```bash
# ✅ Correct
export GROQ_API_KEY="sk-..."
docker-compose up

# ❌ Wrong - hardcoded in Dockerfile
RUN echo "GROQ_API_KEY=sk-..." > .env
```

### 2. Logging & Monitoring

Configure structured logging:

```python
# Already implemented in api.py
# Logs include timestamps, request IDs, status codes
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
```

Set up centralized logging:
- **AWS CloudWatch**: Use CloudWatch agent
- **GCP Cloud Logging**: Auto-configured in Cloud Run
- **Datadog/New Relic**: Use their Python integrations

### 3. Performance Tuning

```yaml
# Production docker-compose with resource limits
services:
  footballiq:
    # ... other config
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### 4. Database Persistence

- **Local**: Use Docker volumes (demonstrated in docker-compose.yml)
- **Cloud**: Use managed services
  - AWS S3 for ChromaDB backups
  - GCP Cloud Storage
  - Azure Blob Storage

### 5. API Rate Limiting

```bash
# Install
pip install slowapi

# Use in api.py (already structure supports it)
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@app.post("/ask")
@limiter.limit("10/minute")
async def ask(request: QueryRequest):
    ...
```

### 6. SSL/TLS Certificates

```bash
# Using Let's Encrypt with Nginx
docker run -d \
  -p 80:80 \
  -p 443:443 \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -e DOMAINS="yourdomain.com" \
  certbot/certbot certonly --standalone
```

### 7. Backups

```bash
# Backup ChromaDB
docker run -v footballiq_chroma_db:/data \
  -v $(pwd)/backups:/backups \
  ubuntu tar czf /backups/chroma_db_$(date +%Y%m%d).tar.gz /data

# Restore from backup
docker run -v footballiq_chroma_db:/data \
  -v $(pwd)/backups:/backups \
  ubuntu tar xzf /backups/chroma_db_YYYYMMDD.tar.gz -C /
```

---

## MONITORING & ALERTING

### Health Check Intervals

```
- Liveness probe: Every 10s after 40s startup
- Readiness probe: Every 5s after 30s startup
- Timeout per check: 10s
```

### Key Metrics to Monitor

1. **Response Time**: Should be <2s for /ask endpoint
2. **Error Rate**: Keep < 0.1%
3. **CPU Usage**: Peak ~70%
4. **Memory Usage**: Should stabilize after startup
5. **Vector DB Size**: Monitor for growth

### Example Alert Rules

```yaml
# Alert if error rate > 1%
alert_error_rate:
  expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.01

# Alert if response time > 5s
alert_slow_response:
  expr: histogram_quantile(0.95, http_request_duration_seconds) > 5

# Alert if pod restarts > 2 in 1 hour
alert_pod_restart:
  expr: rate(container_last_seen[1h]) > 2
```

---

## TROUBLESHOOTING

### App Stuck in "Initializing"

```bash
# Check logs
docker logs footballiq

# Verify data files exist
docker exec footballiq ls -la /app/data/

# Restart service
docker-compose restart
```

### Out of Memory

```bash
# Increase container memory limit
docker-compose.yml:
  services:
    footballiq:
      deploy:
        resources:
          limits:
            memory: 4G
```

### GROQ API Timeout

```bash
# Check API key is valid
curl -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/health

# Increase timeout in .env
LLM_TIMEOUT=60
```

### Vector DB Corruption

```bash
# Rebuild from scratch
rm -rf chroma_db/
docker-compose restart
# Re-run ingest.ipynb
```

---

## CI/CD INTEGRATION

### GitHub Actions Example

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build and push Docker image
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: myregistry/footballiq:${{ github.sha }}
      
      - name: Deploy to ECS
        run: |
          aws ecs update-service \
            --cluster production \
            --service footballiq \
            --force-new-deployment
```

---

## SECURITY CHECKLIST

- [ ] GROQ_API_KEY not committed to git
- [ ] CORS origins restricted to known domains
- [ ] Input validation on all endpoints
- [ ] Rate limiting enabled
- [ ] HTTPS enforced in production
- [ ] Security headers set (X-Content-Type-Options, etc.)
- [ ] Regular dependency updates (dependabot)
- [ ] Container vulnerability scanning
- [ ] Secrets stored in environment, not code

---

## SUPPORT

For issues:
1. Check logs: `docker-compose logs footballiq`
2. Verify health: `curl http://localhost:8000/health`
3. Test API: `curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"query": "test"}'`
