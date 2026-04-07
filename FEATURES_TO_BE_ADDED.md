# Features Roadmap

## Authentication & Authorization
- [x] User login / role-based access (owner, staff, cashier)
- [x] API key management (JWT tokens)
- [x] Session handling

## Multi-Store / Multi-Tenant
- [x] Store-level data isolation (store_id on all models)
- [x] Cross-store analytics / benchmarking

## Real Integrations
- [x] WhatsApp Business API (Twilio/Gupshup)
- [x] UPI/payment gateway (Razorpay)
- [x] GST invoicing / billing compliance
- [x] POS hardware (barcode scanner, receipt printer)
- [x] Tally/accounting software sync

## Notifications
- [x] Push notifications (Web Push / VAPID)
- [x] SMS alerts (MSG91 / Twilio)
- [x] Email digests (aiosmtplib)

## Reporting & Exports
- [x] PDF/Excel report generation
- [x] Date-range filtering on all data
- [x] Profit & loss statements
- [x] GST returns export (GSTR-1, GSTR-3B)

## Customer-Facing
- [x] Customer loyalty / points program
- [x] Digital receipts (WhatsApp/SMS)
- [x] Online ordering / catalog

## Data & Infrastructure
- [x] Proper database (SQLAlchemy async + PostgreSQL)
- [x] Database migrations (Alembic)
- [x] Backup/restore
- [x] Offline-first / sync when connected
- [x] Rate limiting / API throttling

## Ops & Observability
- [x] Error tracking (Sentry)
- [x] Metrics dashboard (Prometheus-compatible)
- [x] Structured logging (JSON + correlation IDs)
- [x] Health checks (liveness, readiness, startup)

## ML / Intelligence Upgrades
- [x] Demand forecasting (exponential smoothing, Holt's double smoothing, seasonality)
- [x] Dynamic pricing engine
- [x] Basket analysis (co-occurrence, lift scoring, cross-sell)
- [x] Image-based shelf audit (Gemini Vision API)
- [x] Voice input for stock updates (Google Cloud STT + Hindi/English)

## Workflow
- [x] Configurable approval chains
- [x] Scheduled reports (daily P&L email)
- [x] Undo/rollback on actions
- [x] Audit log search & filtering

## Mobile
- [x] PWA with offline support (installable, service worker, app shortcuts)
- [x] Barcode scan from phone camera (mobile API)

## Localization
- [x] Hindi / regional language UI (hi, mr, ta, te, kn, bn, gu)
- [x] Multilingual voice commands

## Returns & Refunds
- [x] Return processing workflow
- [x] Refund tracking / credit notes

## Vendor Portal
- [x] Supplier self-service (update prices, confirm orders)
- [x] Digital purchase orders

## Credit Management (Udhaar)
- [x] Payment reminders (automated WhatsApp)
- [x] Credit limit enforcement
- [x] Partial payment tracking
- [x] Interest/late fee rules

## Promotions Engine
- [x] Combo deals / bundle pricing
- [x] Time-bound flash sales (automated start/end)
- [x] Coupon codes

## Staff Management
- [x] Attendance tracking
- [x] Performance metrics per cashier
- [x] Payroll integration (EPF, ESI, Professional Tax)

## Compliance & Security
- [x] Data encryption at rest (Fernet AES)
- [x] DPDP Act compliance (India data privacy)
- [x] Audit log tamper-proofing (SHA-256 hash chain)
- [x] Input sanitization (XSS/injection hardening)

## Testing
- [x] Integration test suite with real DB
- [x] Load/stress testing (Locust)
- [x] E2E browser tests (Playwright)

## Deployment
- [x] CI/CD pipeline (GitHub Actions)
- [x] Docker containerization (multi-stage build)
- [x] One-click deploy (Railway/Render)
- [x] Kubernetes manifests + Helm chart
- [x] Environment management (staging/prod separation)

## Developer Experience
- [x] API documentation (OpenAPI/Swagger with examples)
- [x] API versioning (/api/v1/ with deprecation headers)
- [x] Webhook system for third-party integrations
- [x] Plugin/extension architecture
- [x] WebSocket real-time dashboard updates
- [x] OpenAPI TypeScript client SDK

---

## Completion: ~97%

All major features implemented. Remaining nice-to-haves:

| Feature | Difficulty | Status |
|---------|-----------|--------|
| Native mobile (React Native) | Hard | PWA covers this — native only needed for camera/NFC |
| Redis-backed rate limiter | Medium | Current in-memory works for single-instance |
| PgBouncer connection pooling | Medium | Needed above 4 pods |
| Idempotency keys on payments | Medium | Current offline-sync has op-level idempotency |
