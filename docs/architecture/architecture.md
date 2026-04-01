# Architecture

## Overview

Janus Edge is a web application for importing futures execution exports, reconstructing trades, journaling them, attaching media, and analyzing results.

The codebase is organized as a monorepo with:

- a React and TypeScript frontend in `frontend/`
- a Flask backend in `backend/`
- MongoDB for persisted application data
- MinIO for media object storage
- Docker Compose for local orchestration

## System Diagram

```mermaid
graph TB
	Trader[Trader in Browser]
	Frontend[Frontend<br/>React + Vite]
	Backend[Backend API<br/>Flask]
	Mongo[(MongoDB)]
	MinIO[(MinIO)]
	CSV[NinjaTrader or Quantower CSV]
	TickExport[NinjaTrader Tick Export]

	Trader --> Frontend
	Frontend -->|REST /api| Backend
	Trader -->|Upload| CSV
	Trader -->|Upload| TickExport
	CSV -->|multipart upload| Frontend
	TickExport -->|multipart upload| Frontend
	Backend --> Mongo
	Backend --> MinIO
```

## Runtime Topology

In local development, the main runtime pieces are:

1. The Vite dev server on port `5173`
2. The Flask API on port `5000`
3. MongoDB on port `27017`
4. MinIO on ports `9000` and `9001`

When running the frontend in development mode, browser requests to `/api` are proxied by Vite to the Flask backend.

## Local Runtime Diagram

```mermaid
graph LR
	Browser[Browser :5173]
	Vite[Vite dev server :5173]
	Flask[Flask API :5000]
	Mongo[(MongoDB :27017)]
	MinIOAPI[(MinIO API :9000)]
	MinIOConsole[MinIO Console :9001]

	Browser --> Vite
	Vite -->|Proxy /api| Flask
	Flask --> Mongo
	Flask --> MinIOAPI
	Browser --> MinIOConsole
```

## Main Data Flows

### Authentication

- The frontend calls `/api/auth/*` endpoints.
- The backend issues JWT access tokens.
- The frontend stores the token in `sessionStorage` and attaches it on every API request.

### CSV Import

- A user uploads a CSV export through the import wizard.
- The backend detects the platform format and parses the file.
- Parsed executions are reconstructed into trades.
- On finalization, the backend creates or reuses accounts, writes an import batch, stores executions and trades, and records an audit log entry.

### Trade Review and Journaling

- Trade lists and detail views are loaded from `/api/trades`.
- Trade detail pages load executions plus OHLC data from `/api/market-data/ohlc`.
- Notes, tags, initial risk, wish-stop, and target values are stored on the trade document.

### Media Attachments

- File metadata is stored in MongoDB in the `media` collection.
- Binary file content is stored in MinIO.
- The backend returns presigned download URLs for access.

### Analytics and What-If

- Analytics endpoints aggregate trade data from MongoDB.
- What-if endpoints reuse persisted trade and stored market-data information to calculate stop overshoot statistics and wider-stop simulations. The stop-management simulator supports replay from stored 1-minute candles or stored raw ticks.
- Monte Carlo simulation is computed in the backend and rendered by the frontend.

### Backup and Restore

- Export creates a ZIP archive containing `manifest.json`, `data.json`, and media binaries.
- Restore merges that archive into the authenticated destination user.
- Portable user settings such as timezones, starting equity, and symbol mappings are restored as part of that flow.

## Import And Backup Flows

```mermaid
flowchart TD
	Upload[Upload CSV] --> Detect[Detect platform]
	Detect --> Parse[Parse executions]
	Parse --> Reconstruct[Reconstruct trades]
	Reconstruct --> Finalize[Finalize import]
	Finalize --> Accounts[Create or reuse accounts]
	Finalize --> Batches[Create import batch]
	Finalize --> Executions[Persist executions]
	Finalize --> Trades[Persist trades]
	Finalize --> Audit[Write audit log]
```

```mermaid
flowchart LR
	UserData[User data in MongoDB]
	MediaData[Media in MinIO]
	Export[Portable export]
	Zip[ZIP with manifest.json, data.json, media/]
	Restore[Merge restore into current user]

	UserData --> Export
	MediaData --> Export
	Export --> Zip
	Zip --> Restore
```

## Code-Level Component Map

### Frontend

- `src/pages/`: route-level views such as Dashboard, Trades, Import, Analytics, What-if, and Settings
- `src/api/`: thin HTTP wrappers around backend endpoints
- `src/contexts/`: auth, filters, theme, and toast state
- `src/components/`: reusable UI, charts, trade, analytics, import, and layout components

### Backend

- `app/__init__.py`: Flask app factory and blueprint registration
- `app/auth/`: authentication plus backup export and restore
- `app/imports/`: CSV upload, parsing, reconstruction, and import finalization
- `app/trades/`: trade CRUD and search
- `app/analytics/`: reporting and Monte Carlo simulation
- `app/market_data/`: stored market-data retrieval and candle access
- `app/media/`: upload, listing, URL generation, and deletion for trade media
- `app/whatif/`: stop analysis and simulation endpoints
- `app/repositories/`: MongoDB data-access layer
- `app/models/`: document-construction helpers used before inserts

## Storage Responsibilities

### MongoDB

MongoDB stores the application records for:

- users
- trade accounts
- import batches
- executions
- trades
- tags
- market-data dataset metadata
- media metadata
- audit logs

### MinIO

MinIO stores the binary media files for trade attachments.

The bucket is created automatically on backend startup if the MinIO client can connect and the bucket does not already exist.

## Architecture Boundaries That Are Not Yet Fully Defined

The repository does not currently contain:

- a production reverse proxy configuration
- deployment manifests for Kubernetes or another orchestrator
- a dedicated background job system
- a separate worker process for imports or analytics

Those pieces should be treated as TODO items rather than current architecture guarantees.

## Complete System Diagram Set

### Source System Context Diagram

```mermaid
C4Context
	title System Context Diagram — Janus Edge

	Person(trader, "Trader", "A futures trader who imports trade execution files, journals trades, and reviews analytics")

	System(janusedge, "Janus Edge Web App", "Trade journaling and analytics platform. React SPA + Flask API + MongoDB")

	System_Ext(ninjatrader, "NinjaTrader", "Trading platform that exports execution-level CSV files")
	System_Ext(ninjatraderticks, "NinjaTrader Tick Export", "Text exports containing raw tick market data")
	System_Ext(quantower, "Quantower", "Trading platform that exports execution-level CSV files")

	Rel(trader, janusedge, "Uses browser to", "HTTPS")
	Rel(trader, ninjatrader, "Exports CSV files from")
	Rel(trader, ninjatraderticks, "Exports tick data from")
	Rel(trader, quantower, "Exports CSV files from")
	Rel(trader, janusedge, "Uploads CSV files to")
	Rel(trader, janusedge, "Uploads tick data to")
	Rel(trader, janusedge, "Downloads portable backups from")
	Rel(trader, janusedge, "Restores portable backups into")
```

### Source Component Architecture Diagram

```mermaid
graph TB
	subgraph Frontend ["Frontend (React SPA)"]
		direction TB
		App[App Shell<br/>Router + Auth Context]
        
		subgraph Pages ["Pages"]
			Login[Login / Register]
			Dashboard[Dashboard]
			TradeList[Trade List]
			TradeDetail[Trade Detail + Chart + Stop Analysis]
			Import[CSV Import Wizard]
			Analytics[Analytics Dashboard]
			Settings[Settings]
			ManualTrade[Manual Trade Entry]
			Backup[Portable Backup / Restore]
		end
        
		subgraph Components ["Shared Components"]
			Chart[CandlestickChart<br/>Lightweight Charts]
			DataTable[DataTable<br/>Sortable/Filterable]
			FileUpload[FileUpload<br/>Drag & Drop]
			FilterBar[FilterBar<br/>Account/Symbol/Tag]
			TradeForm[TradeForm<br/>Create/Edit]
			CalendarHeatmap[CalendarHeatmap]
			EquityCurve[EquityCurve Chart]
		end
        
		subgraph Services_FE ["Frontend Services"]
			APIClient[API Client<br/>Axios + JWT interceptor]
			AuthService[Auth Service]
		end
        
		App --> Pages
		Pages --> Components
		Pages --> Services_FE
	end
    
	subgraph Backend ["Backend (Flask API)"]
		direction TB
		FlaskApp[Flask App<br/>CORS + JWT Middleware]
        
		subgraph Routes ["API Routes - Blueprints"]
			AuthRoutes["auth routes"]
			ImportRoutes["imports routes"]
			TradeRoutes["trades routes"]
			ExecutionRoutes["executions routes"]
			AccountRoutes["accounts routes"]
			AnalyticsRoutes["analytics routes"]
			MarketDataRoutes["market-data routes"]
			BackupRoutes["auth settings + backup routes"]
		end
        
		subgraph Services_BE ["Business Services"]
			CSVParser[CSV Parser Service<br/>Platform detection & parsing]
			TradeReconstructor[Trade Reconstruction Engine<br/>FIFO/LIFO/Weighted Avg]
			MarketDataService[Market Data Service<br/>stored candles + datasets]
			TickDataService[Tick Data Service<br/>tick import + replay data]
			AnalyticsEngine[Analytics Engine<br/>Metrics computation]
			ImportService[Import Service<br/>Batch management]
			BackupService[Portable Backup Service<br/>ZIP export + merge restore]
		end
        
		subgraph Repositories ["Data Repositories"]
			UserRepo[User Repository]
			TradeRepo[Trade Repository]
			ExecutionRepo[Execution Repository]
			ImportBatchRepo[Import Batch Repository]
			AccountRepo[Account Repository]
			MarketDataRepo[Market Data Dataset Repository]
			AuditRepo[Audit Log Repository]
		end
        
		FlaskApp --> Routes
		Routes --> Services_BE
		Services_BE --> Repositories
	end
    
	subgraph Database ["MongoDB"]
		direction TB
		UsersCol[(users)]
		TradesCol[(trades)]
		ExecutionsCol[(executions)]
		ImportBatchesCol[(import_batches)]
		TradeAccountsCol[(trade_accounts)]
		MarketDataDatasetsCol[(market_data_datasets)]
		AuditLogsCol[(audit_logs)]
		TagsCol[(tags)]
	end
    
	Services_FE -->|REST API| FlaskApp
	Repositories --> Database
	MarketDataService --> MinIOStore["MinIO market-data objects"]
	TickDataService --> MinIOStore
```

### Source Deployment Architecture Diagram

```mermaid
graph TB
	subgraph DockerCompose ["Docker Compose (Local Development)"]
		subgraph FrontendContainer ["frontend container"]
			Vite["Vite Dev Server<br/>:5173"]
		end
        
		subgraph BackendContainer ["backend container"]
			Flask["Flask Dev Server<br/>:5000"]
		end
        
		subgraph MongoContainer ["mongo container"]
			MongoDB["MongoDB 7.x<br/>:27017"]
		end
        
		subgraph MinIOContainer ["minio container"]
			MinIO["MinIO<br/>:9000 API / :9001 Console"]
		end
        
		subgraph MongoVolume ["mongo-data volume"]
			PersistentData["Persistent Data"]
		end
        
		subgraph MinIOVolume ["minio-data volume"]
			ObjectData["Object Data"]
		end
        
		Vite -->|"Proxy /api → backend:5000"| Flask
		Flask -->|"mongo:27017"| MongoDB
		Flask -->|"minio:9000"| MinIO
		MongoDB --> PersistentData
		MinIO --> ObjectData
	end
    
	subgraph Production ["Production Deployment (Future)"]
		subgraph WebServer ["Web Server"]
			Nginx["Nginx<br/>Reverse Proxy + Static Files"]
		end
        
		subgraph AppServer ["Application Server"]
			Gunicorn["Gunicorn<br/>Flask WSGI"]
		end
        
		subgraph DBProd ["Database"]
			MongoProd["MongoDB<br/>(Atlas or self-hosted)"]
		end
        
		Nginx -->|"/api/*"| Gunicorn
		Nginx -->|"Static React Build"| StaticFiles["React Build Artifacts"]
		Gunicorn --> MongoProd
	end
```

### Source Data Flow Diagram

```mermaid
flowchart TB
	subgraph Import ["CSV Import Flow"]
		A[User uploads CSV file] --> B[Platform auto-detection<br/>by header patterns]
		B --> C[Column mapping & parsing]
		C --> D[Row validation & normalization]
		D --> E[Duplicate detection<br/>file hash + execution IDs]
		E --> F[Trade account auto-discovery]
		F --> G[Trade reconstruction<br/>flat-to-flat grouping]
		G --> H[Fee entry screen<br/>per reconstructed trade]
		H --> I[Confirm & persist<br/>executions + trades + batch]
	end
    
	subgraph Storage ["Data Storage"]
		I --> J[(executions collection)]
		I --> K[(trades collection)]
		I --> L[(import_batches collection)]
		I --> M[(trade_accounts collection)]
	end
    
	subgraph MarketData ["Market Data Flow"]
		N[User uploads tick export] --> O[Parse and validate tick rows]
		O --> P[Store raw ticks in MinIO]
		P --> Q[Derive candle datasets]
		Q --> R[Write dataset metadata to MongoDB]
		R --> S[Return tick and candle availability to frontend]
		S --> T[Use candles for charts and ticks for What-If replay]
	end
    
	subgraph Analytics ["Analytics Flow"]
		U[User opens Analytics] --> V[Fetch trades with filters<br/>account/symbol/tag/date]
		V --> W[Compute metrics server-side<br/>win rate, P&L, expectancy]
		W --> X[Return aggregated data]
		X --> Y[Render charts & tables]
	end
```

### Source Sequence Diagram: CSV Import

```mermaid
sequenceDiagram
	actor User
	participant FE as React Frontend
	participant API as Flask API
	participant Parser as CSV Parser Service
	participant Recon as Trade Reconstructor
	participant DB as MongoDB
    
	User->>FE: Drag & drop CSV file
	FE->>API: POST /api/imports/upload (multipart file)
	API->>Parser: detect_platform(file_content)
	Parser-->>API: platform_type, delimiter, columns
	API->>Parser: parse_executions(file, platform)
	Parser-->>API: parsed_executions[], errors[]
	API->>DB: Check file hash (duplicate detection)
	DB-->>API: is_duplicate: false
	API-->>FE: Preview: executions + validation results
    
	User->>FE: Confirm import
	FE->>API: POST /api/imports/confirm
	API->>DB: Upsert trade accounts
	API->>Recon: reconstruct_trades(executions)
	Recon-->>API: reconstructed_trades[]
	API-->>FE: Show trades with fee entry fields
    
	User->>FE: Enter fees, click "Import"
	FE->>API: POST /api/imports/finalize {trades_with_fees}
	API->>DB: Insert executions
	API->>DB: Insert trades (with fees)
	API->>DB: Insert import_batch record
	API->>DB: Insert audit_log entries
	API-->>FE: Import complete summary
```

### Source Sequence Diagram: Trade Detail With Chart

```mermaid
sequenceDiagram
	actor User
	participant FE as React Frontend
	participant Chart as Lightweight Charts
	participant API as Flask API
	participant MDS as Market Data Service
	participant Repo as Dataset Metadata Repository
	participant MinIO as MinIO

	User->>FE: Navigate to trade detail
	FE->>API: GET /api/trades/{id}
	API-->>FE: trade data + executions
    
	FE->>API: GET /api/market-data/ohlc?symbol=MES&interval=5m&start=...&end=...
	API->>MDS: get_ohlc(symbol, interval, start, end)
	MDS->>Repo: Find candle datasets for symbol/interval/range
    
	alt Datasets found
		Repo-->>MDS: dataset metadata
		MDS->>MinIO: Read Parquet candle objects
		MinIO-->>MDS: candle rows
	else No datasets
		Repo-->>MDS: no matching datasets
	end
    
	MDS-->>API: OHLC data array
	API-->>FE: OHLC JSON response
     
	FE->>Chart: createChart(container)
	FE->>Chart: addSeries(CandlestickSeries)
	FE->>Chart: setData(ohlc_data)
	FE->>Chart: Add entry/exit markers
	Chart-->>User: Rendered chart with markers

	opt User clicks Detect on wishful stop
		FE->>API: POST /api/trades/{id}/detect-wish-stop
		API->>MDS: read stored 1m candle data for trade day
		MDS->>Repo: find candle dataset metadata
		Repo-->>MDS: candle dataset metadata
		MDS->>MinIO: Read Parquet candle object
		MinIO-->>MDS: ordered candle rows
		MDS-->>API: replayable OHLC bars
		API-->>FE: { wish_stop_price }
	end
```

### Source Sequence Diagram: Authentication

```mermaid
sequenceDiagram
	actor User
	participant FE as React Frontend
	participant API as Flask API
	participant DB as MongoDB

	User->>FE: Enter username + password
	FE->>API: POST /api/auth/register {username, password, timezone}
	API->>DB: Check username exists
	DB-->>API: not found
	API->>DB: Insert user (hashed password)
	API-->>FE: JWT token + user profile
	FE->>FE: Store JWT in memory/cookie
    
	Note over User,FE: Subsequent requests
	FE->>API: GET /api/trades (Authorization: Bearer JWT)
	API->>API: Verify JWT, extract user_id
	API->>DB: Query trades where user_id matches
	API-->>FE: trades[]
```

### Source Entity Relationship Diagram

```mermaid
erDiagram
	USERS {
		ObjectId _id PK
		string username UK
		string password_hash
		string timezone
		datetime created_at
		datetime updated_at
	}
    
	TRADE_ACCOUNTS {
		ObjectId _id PK
		ObjectId user_id FK
		string account_name
		string display_name
		string notes
		string status "active|archived"
		datetime created_at
	}
    
	IMPORT_BATCHES {
		ObjectId _id PK
		ObjectId user_id FK
		string file_name
		string file_hash
		string platform "ninjatrader|quantower"
		int total_rows
		int imported_rows
		int skipped_rows
		int error_rows
		int trades_reconstructed
		object column_mapping
		string reconstruction_method "FIFO|LIFO|WAVG"
		datetime imported_at
	}
    
	EXECUTIONS {
		ObjectId _id PK
		ObjectId user_id FK
		ObjectId trade_id FK
		ObjectId import_batch_id FK
		ObjectId trade_account_id FK
		string symbol
		string side "Buy|Sell"
		int quantity
		float price
		datetime timestamp
		string platform_execution_id
		string platform_order_id
		string order_type "Market|Limit|Stop"
		string entry_exit "Entry|Exit"
		object raw_data
		datetime created_at
	}
    
	TRADES {
		ObjectId _id PK
		ObjectId user_id FK
		ObjectId trade_account_id FK
		ObjectId import_batch_id FK
		string symbol
		string side "Long|Short"
		int total_quantity
		int max_quantity
		float avg_entry_price
		float avg_exit_price
		float gross_pnl
		float fee
		string fee_source "csv|import_entry|manual_edit"
		float net_pnl
		datetime entry_time
		datetime exit_time
		int holding_time_seconds
		int execution_count
		string source "imported|manual"
		boolean manually_adjusted
		string status "open|closed|deleted"
		string[] tag_ids
		string strategy
		string pre_trade_notes
		string post_trade_notes
		object[] attachments
		datetime created_at
		datetime updated_at
		datetime deleted_at
	}
    
	TAGS {
		ObjectId _id PK
		ObjectId user_id FK
		string name
		string category "strategy|mistake|market_condition|custom"
		string color
		datetime created_at
	}
    
	MARKET_DATA_DATASETS {
		ObjectId _id PK
		string symbol
		string raw_symbol
		string dataset_type "ticks|candles"
		string timeframe "1m|5m|15m|1h|null"
		date date
		string object_key
		int row_count
		int byte_size
		string source_file_name
		string import_batch_id
		string status
		datetime created_at
		datetime updated_at
	}
    
	AUDIT_LOGS {
		ObjectId _id PK
		ObjectId user_id FK
		string action "import|fee_edit|trade_edit|delete|restore"
		string entity_type "trade|execution|import_batch"
		ObjectId entity_id FK
		object old_values
		object new_values
		datetime timestamp
	}
    
	USERS ||--o{ TRADE_ACCOUNTS : "has"
	USERS ||--o{ IMPORT_BATCHES : "imports"
	USERS ||--o{ TRADES : "owns"
	USERS ||--o{ EXECUTIONS : "owns"
	USERS ||--o{ TAGS : "creates"
	USERS ||--o{ AUDIT_LOGS : "generates"
	TRADE_ACCOUNTS ||--o{ TRADES : "contains"
	TRADE_ACCOUNTS ||--o{ EXECUTIONS : "contains"
	IMPORT_BATCHES ||--o{ EXECUTIONS : "produces"
	IMPORT_BATCHES ||--o{ TRADES : "produces"
	TRADES ||--o{ EXECUTIONS : "composed of"
	TRADES }o--o{ TAGS : "tagged with"
```
