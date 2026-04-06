# Lab — app cu 3 straturi (frontend, backend, DB)

Proiect minimal pentru **Laborator 4 (CI/CD pe Google Cloud)**: aplicație web cu **trei componente în containere separate**, mapate pe **poduri distincte** în Kubernetes (GKE): nginx (frontend), FastAPI (backend), PostgreSQL.

**Raport (RO):** [`docs/RAPORT_LABORATOR_CI_CD.md`](docs/RAPORT_LABORATOR_CI_CD.md) — obiective, arhitectură, pași CI/CD, GCP, probleme întâlnite, acces cluster.

## Arhitectură

```text
Browser → [Service: frontend / LoadBalancer] → pod nginx
                    → proxy /api → [Service: backend] → pod FastAPI
                                              → [Service: postgres] → pod PostgreSQL
```

Frontend-ul apelează API-ul prin **aceeași origine** (`/api/...`); nginx face proxy către serviciul Kubernetes `backend:8000`, astfel nu este nevoie de CORS pentru browser.

## Structură

| Director    | Rol |
|------------|-----|
| `frontend/` | HTML static + nginx; `location /api` → backend |
| `backend/`  | FastAPI + SQLAlchemy + PostgreSQL |
| `k8s/`      | Manifeste: namespace `lab`, Postgres, backend, frontend (LoadBalancer) |
| `cloudbuild.yaml` | Exemplu build imagini în Artifact Registry |

## Rulare locală (Docker Compose)

Un singur host: trei containere (echivalent „trei servicii”; pe GKE fiecare devine pod).

```bash
docker compose up --build
```

- UI: [http://localhost:8080](http://localhost:8080)  
- API direct (opțional): [http://localhost:8000/docs](http://localhost:8000/docs)

### Kubernetes local (kind)

Același `k8s/` ca în cloud, cu cluster **kind** pe mașina ta.

**Cerințe:** [Docker](https://docs.docker.com/get-docker/), [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation), `kubectl`.

```bash
./scripts/local-k8s-kind.sh
```

Scriptul pornește singur **`kubectl port-forward`** la final — deschide [http://localhost:8080](http://localhost:8080) în browser (același terminal rămâne ocupat; **Ctrl+C** oprește tunelul). Pentru doar deploy fără port-forward: `SKIP_PORT_FORWARD=1 ./scripts/local-k8s-kind.sh`.

Ștergere cluster: `kind delete cluster --name lab-local`.

**Alternativă — minikube:** `minikube start`, construiește imaginile în daemon-ul minikube (`eval "$(minikube docker-env)"`), apoi `docker build …`, `kubectl apply -k k8s/`, apoi `minikube service frontend -n lab` sau `kubectl port-forward` ca mai sus.

## Kubernetes (GKE)

1. Creează Artifact Registry și împinge imaginile `backend` / `frontend` acolo (manual, Cloud Build sau GitHub Actions).
2. Manifestele folosesc temporar `lab/backend:latest` și `lab/frontend:latest`; după primul `kubectl apply -k k8s/`, setează imaginile reale, de exemplu:  
   `kubectl set image deployment/backend backend=REGION-docker.pkg.dev/PROJECT/REPO/backend:TAG -n lab` (și la fel pentru `frontend`). Workflow-ul GitHub Actions face acest pas automat.
3. Aplică manifestele:

```bash
kubectl apply -k k8s/
```

4. Așteaptă IP-ul LoadBalancer-ului pentru serviciul `frontend` în namespace-ul `lab`:

```bash
kubectl get svc -n lab frontend
```

Deschide `http://EXTERNAL_IP` în browser.

**Notă:** Parola DB din `k8s/postgres.yaml` este un exemplu; pentru producție folosește Secret gestionat (Secret Manager / Workload Identity) și rotește credențialele.

## CI/CD (Cloud Build)

Repository-ul conține `cloudbuild.yaml` care construiește imaginile `backend` și `frontend` și le publică în Artifact Registry. Leagă un trigger Git pe acest fișier și setează substituțiile `_REGION` și `_REPO`.

## CI/CD (GitHub Actions → GKE)

Workflow-ul [`.github/workflows/deploy-gke.yml`](.github/workflows/deploy-gke.yml) face: **build Docker** → **push în Artifact Registry** → **`kubectl apply`** (Postgres + servicii) → **`kubectl set image`** pentru backend/frontend → **rollout**.

**Ghid pas cu pas** (secrete, variabile, WIF, link-uri oficiale): [`docs/SETUP_GITHUB_GCP.md`](docs/SETUP_GITHUB_GCP.md).

**Variantă „copy-paste”** (un singur lucru de înlocuit: `TAI_PROIECT_ID` / număr proiect): [`docs/GITHUB_GCP_COPY_PASTE.md`](docs/GITHUB_GCP_COPY_PASTE.md).

### Ce îți trebuie în Google Cloud

1. **Proiect GCP** cu facturare activă (sau trial), API-uri pornite: Artifact Registry, Kubernetes Engine, IAM, Cloud Resource Manager.
2. **Artifact Registry**: un repository Docker (ex. `lab-app`) în regiunea aleasă (aceeași cu `GCP_REGION`).
3. **Cluster GKE** (regional sau zonal); notează **numele** clusterului și **locația** (`GKE_LOCATION`: regiune sau zonă).
4. **Workload Identity Federation (WIF)** între GitHub și GCP (fără cheie JSON în repo):
   - Creezi un **Workload Identity Pool** + **OIDC provider** pentru `https://token.actions.githubusercontent.com`, restricționat la org/repo și opțional la ramura `main`.
   - Creezi un **service account** GCP și îi dai minim: `roles/artifactregistry.writer`, `roles/container.developer`.
   - Legi principalul WIF la acel service account (`roles/iam.workloadIdentityUser` pe SA pentru principalul GitHub).

   Pașii exacti sunt în documentația Google: [Workload Identity Federation with deployment pipelines](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

### Ce configurezi în GitHub

**Secrets** (repository sau environment):

| Secret | Exemplu |
|--------|---------|
| `WIF_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/providers/PROVIDER_ID` |
| `WIF_SERVICE_ACCOUNT` | `nume-sa@PROJECT_ID.iam.gserviceaccount.com` |

**Variables** (Actions → Variables):

| Variable | Exemplu |
|----------|---------|
| `GCP_PROJECT_ID` | `my-project-123` |
| `GCP_REGION` | `europe-west1` |
| `AR_REPO` | `lab-app` (id-ul repository-ului din Artifact Registry) |
| `GKE_CLUSTER_NAME` | `lab-cluster` |
| `GKE_LOCATION` | `europe-west1` sau `europe-west1-b` |

După push pe `main` (sau rulare manuală **Actions → Deploy to GKE → Run workflow**), pipeline-ul publică imaginile la  
`${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/backend|frontend:${GITHUB_SHA}`  
și actualizează deployment-urile din namespace-ul `lab`.

### Variante

- **Autentificare cu cheie JSON** (mai puțin recomandat): înlocuiești pasul `google-github-actions/auth` cu `credentials_json: ${{ secrets.GCP_SA_KEY }}` și pui conținutul cheii în secretul `GCP_SA_KEY`. Service account-ul trebuie să aibă aceleași roluri ca mai sus.
- **Cloud Run** în loc de GKE: același build/push, dar deploy cu `gcloud run deploy` (un serviciu per container sau rețea VPC); manifestele din `k8s/` sunt pentru GKE.

### Observații

- Nodurile GKE din același proiect pot trage imagini din Artifact Registry fără configurare suplimentară, de obicei.
- Cluster **private endpoint** nu e accesibil din runner-ul public GitHub fără VPN/Cloud Build/bastion — pentru laborator, folosește un cluster cu endpoint public sau un alt mecanism de acces.

## API

| Metodă | Cale | Descriere |
|--------|------|-----------|
| GET | `/health` | Health check |
| GET | `/api/items` | Listă item-uri |
| POST | `/api/items` | Creare (`{"title": "...", "note": "..."}`) |
| GET | `/api/items/{id}` | Detaliu |
