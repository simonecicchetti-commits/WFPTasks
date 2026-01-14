# Formulario de Onboarding de Soluciones Digitales
## Food Security Crisis Observatory - WFP World Food Program
### Versión 2.0 - 2026-01-14

---

El propósito de este documento es recopilar información clave que permita al equipo de IDBCloud4LAC analizar las necesidades técnicas, operativas y estratégicas de la Solución Digital.

> **Nota:** Las secciones 2, 3 y 5 han sido completadas por el equipo técnico de la Solución Digital.

---

## 1. Información General

| Campo | Respuesta |
|-------|-----------|
| **1.1 Nombre de la Solución Digital** | Food Security Crisis Observatory - WFP World Food Program |
| **1.2 Nombre corto de la Solución** | Food Security Crisis Observatory |
| **1.3 Departamento / División** | IFD/CMF |
| **1.4 Owner de la solución** | *[Pendiente - Nombre y correo]* |
| **1.5 Otros integrantes del equipo IDB** | *[Pendiente - Nombre, Rol, Correo]* |
| **1.6 Technology and Transformation Advisor (TTA)** | Roig Rodriguez |
| **1.7 Consultoría a cargo del desarrollo** | *[Pendiente - Nombre, país, sitio web]* |
| **1.8 Institución(es) receptora(s)** | World Food Programme (WFP), Global |
| **1.9 Países beneficiarios** | **9 países LAC:** Belice (BLZ), Bolivia (BOL), República Dominicana (DOM), Ecuador (ECU), Guatemala (GTM), Honduras (HND), Haití (HTI), Nicaragua (NIC), El Salvador (SLV) |
| **1.10 Breve descripción de la funcionalidad** | Sistema integral de monitoreo de seguridad alimentaria para América Latina y el Caribe. Recopila datos de múltiples fuentes (APIs externas, encuestas RTM), procesa indicadores de seguridad alimentaria (FCS, rCSI), conflictos, clima, y desastres naturales. Genera alertas automáticas mediante sistema de triggers y exporta datos para visualización en Tableau. Base de datos con ~3.7 millones de registros, 79 tablas, 6 esquemas. |
| **1.11 Fecha estimada despliegue IDBCloud4LAC** | *[Pendiente]* |
| **1.12 Meses estimados de apoyo** | *[Pendiente]* |
| **1.13 Fuente de financiamiento** | *[Pendiente]* |
| **1.14 Instituciones socias** | WFP (World Food Programme) |

---

## 2. Arquitectura

### 2.1 Diagrama de arquitectura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FOOD SECURITY CRISIS OBSERVATORY                          │
│                         Arquitectura del Sistema                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                        FUENTES DE DATOS EXTERNAS                      │  │
│   ├──────────────────────────────────────────────────────────────────────┤  │
│   │  ADAM API        ACLED API       PDC API        HungerMap API        │  │
│   │  (Hazards)       (Conflict)      (Hazards)      (Food Security)      │  │
│   │                                                                       │  │
│   │  World Bank      FAO             GDACS          Panama Darien        │  │
│   │  (Economic)      (IPC/POU)       (Disasters)    (Migration)          │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                         CAPA DE INGESTION                             │  │
│   │                        (OpenShift CronJobs)                           │  │
│   ├──────────────────────────────────────────────────────────────────────┤  │
│   │  hazard_pipe.py   conflict_pipe.py   economic_pipe.py   hml_pipe.py  │  │
│   │  climate_pipe.py  migration_pipe.py  food_security_pipe.py           │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                      AWS RDS MySQL (eu-west-1)                        │  │
│   ├──────────────────────────────────────────────────────────────────────┤  │
│   │  Schema: idb              Schema: rtm_raw        Schema: rtm_clean   │  │
│   │  ├─ 44 tablas             ├─ 15 tablas           ├─ 12 tablas        │  │
│   │  ├─ 5 vistas SQL          └─ Raw survey data     └─ Cleaned data     │  │
│   │  └─ ~2M registros                                                     │  │
│   │                                                                       │  │
│   │  Schema: rtm_analytics    Schema: rbp            Schema: caricom     │  │
│   │  ├─ 6 tablas              ├─ 1 tabla             ├─ 1 tabla          │  │
│   │  └─ Aggregated data       └─ Hotspot analysis    └─ Inflation data   │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                       SISTEMA DE TRIGGERS                             │  │
│   ├──────────────────────────────────────────────────────────────────────┤  │
│   │  Genera alertas automáticas basadas en umbrales:                      │  │
│   │  ├─ RBP_climate_alert      (8,479 alertas)                           │  │
│   │  ├─ RBP_conflict_alert     (7,496 alertas)                           │  │
│   │  ├─ RBP_economic_alert     (30,810 alertas)                          │  │
│   │  ├─ RBP_food_security_alert (13,222 alertas)                         │  │
│   │  ├─ RBP_hazard_alert       (3,811 alertas)                           │  │
│   │  └─ RBP_trigger_result     (683 resultados)                          │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                           OUTPUTS                                     │  │
│   ├──────────────────────────────────────────────────────────────────────┤  │
│   │  FastAPI REST Endpoints        Tableau Export (RBP_IDB_tableau)      │  │
│   │  ├─ /api/triggers              ├─ 13,275 registros                   │  │
│   │  ├─ /api/alerts                └─ 22 columnas                        │  │
│   │  └─ /api/countries                                                    │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Tecnologías utilizadas

| Categoría | Tecnología | Versión | Propósito |
|-----------|------------|---------|-----------|
| **Lenguaje** | Python | 3.9+ | Backend, procesamiento de datos |
| **Framework API** | FastAPI | 0.100+ | REST API endpoints |
| **Base de Datos** | MySQL | 8.0 | Almacenamiento principal |
| **ORM** | SQLAlchemy | 2.0.36 | Mapeo objeto-relacional |
| **Driver MySQL** | PyMySQL | 1.1.1 | Conexión a base de datos |
| **Procesamiento** | Pandas | 2.1.1 | Manipulación de datos |
| **Procesamiento** | NumPy | 1.26.4 | Cálculos numéricos |
| **Contenedores** | Docker | Latest | Containerización |
| **Orquestación** | OpenShift | 4.x | Deployment y CronJobs |
| **Cloud** | AWS RDS | MySQL 8.0 | Base de datos gestionada |

### 2.3 Licenciamiento de pago

**No.** Todas las tecnologías utilizadas son **open source**:
- Python: PSF License
- FastAPI: MIT License
- MySQL: GPL (Community Edition)
- Pandas, NumPy: BSD License
- SQLAlchemy: MIT License

**No se requiere ningún licenciamiento de pago** para el funcionamiento de la solución.

### 2.4 Integración de APIs externas

**Sí.** La solución integra las siguientes APIs externas:

| API | Proveedor | Datos | Autenticación | Registros |
|-----|-----------|-------|---------------|-----------|
| **ADAM API** | WFP/EU | Terremotos, Inundaciones, Ciclones | No requerida | 221 |
| **ACLED** | Armed Conflict Location | Conflictos armados, protestas | API Key | 68,111 |
| **PDC** | Pacific Disaster Center | Amenazas activas | Usuario/Password | 135 |
| **HungerMap** | WFP | Alertas seguridad alimentaria | No requerida | 68,909 |
| **World Bank** | World Bank Group | Indicadores económicos | No requerida | 59,950 |
| **FAO** | UN FAO | IPC, Prevalencia desnutrición | No requerida | 474 |
| **GDACS** | EU JRC | Desastres globales | No requerida | Integrado |
| **Panama Darien** | Gobierno Panamá | Datos migración | No requerida | 1,935 |
| **US CBP** | US Government | Encuentros fronterizos | No requerida | 54,286 |

---

## 3. Infraestructura

| Campo | Respuesta |
|-------|-----------|
| **3.1 Proveedor de nube** | **AWS** (RDS MySQL) + **OpenShift** (WFP managed containers) |
| **3.2 Ambientes requeridos** | **Development (dev)** y **Production (prod)** - ambos actualmente operativos |
| **3.3 Infraestructura como Código** | Dockerfile para containerización. Manifests de OpenShift para deployment. No se utiliza Terraform/CloudFormation actualmente. |
| **3.4 Dominios/subdominios** | *[Pendiente - Verificar con IT]* |
| **3.5 Certificados SSL** | **Sí** - HTTPS habilitado en OpenShift mediante certificados gestionados |
| **3.6 Control de versiones** | **GitHub** - Repositorio: `github.com/wfp-rbp/RBP_IDB` |
| **3.7 Disaster Recovery** | *[Pendiente - Verificar RTO/RPO con IT]* - AWS RDS tiene backups automáticos |
| **3.8 Servicios terceros SaaS/PaaS** | **AWS RDS MySQL** (PaaS) - Base de datos gestionada en eu-west-1 |
| **3.9 Usuarios simultáneos estimados** | Estimado: 10-50 usuarios concurrentes (principalmente acceso via Tableau) |
| **3.10 Envío de correos** | *[Pendiente - Verificar si se requiere]* |
| **3.11 Costo estimado infraestructura** | *[Pendiente - Solicitar a Finance]* |

### Detalles de Infraestructura Actual

```
DESARROLLO (dev):
├── Host: rdp-idb-dev.chsu4ma0ibqc.eu-west-1.rds.amazonaws.com
├── Puerto: 3306
├── Región: eu-west-1 (Irlanda)
└── Acceso: Requiere VPN WFP

PRODUCCIÓN (prod):
├── Host: rbp-idb-prod.cxai6uauo3yn.eu-west-1.rds.amazonaws.com
├── Puerto: 3306
├── Región: eu-west-1 (Irlanda)
└── Acceso: Requiere VPN WFP

OPENSHIFT (Contenedores):
├── CronJobs para fetchers (ingesta de datos)
├── Deployment para API FastAPI
└── Gestión automática de escalado
```

---

## 4. Privacidad y Protección de Datos

| Campo | Respuesta |
|-------|-----------|
| **4.1 Datos de autenticación** | **Sí** - Credenciales de base de datos almacenadas en variables de entorno (environment variables). No se almacenan contraseñas de usuarios finales. |
| **4.2 Datos personales** | **No** - La solución solo maneja datos agregados a nivel de país (adm0) y región (adm1). No se recopilan nombres, apellidos, ni información personal identificable. |
| **4.3 Bases de datos externas** | **Sí** - AWS RDS MySQL (privada, acceso solo via VPN WFP). APIs externas son públicas o con acceso autorizado. |
| **4.4 Formato bases de datos externas** | Base de datos relacional MySQL + APIs REST (JSON). Algunos datos georreferenciados (coordenadas lat/lon). |
| **4.5 Contacto con Data Privacy** | *[Pendiente]* |

### Clasificación de Datos

| Tipo de Dato | Nivel | Ejemplo |
|--------------|-------|---------|
| Indicadores país | Público | FCS promedio Guatemala: 45.2 |
| Alertas | Interno | Trigger activado para Honduras |
| Credenciales | Confidencial | Variables de entorno |
| PII | **No aplica** | No se recopila información personal |

---

## 5. Seguridad

| Campo | Respuesta |
|-------|-----------|
| **5.1 Resultados SonarQube** | *[Pendiente - Ejecutar análisis]* |
| **5.2 Pruebas WebScan/Pentest** | *[Pendiente]* |
| **5.3 Modelo de autenticación** | Acceso a base de datos mediante credenciales en environment variables. API interna sin autenticación de usuario final (acceso solo desde red WFP). |
| **5.4 Gestión de secretos** | Variables de entorno en OpenShift. *[Considerar migración a AWS Secrets Manager]* |
| **5.5 Configuración especial seguridad** | Base de datos en VPC privada AWS. Acceso solo via VPN WFP. Security Groups restrictivos. |
| **5.6 Pruebas realizadas** | Pruebas unitarias básicas. Pruebas de integración con APIs externas. |

---

## 6. Marca y Comunicación

| Campo | Respuesta |
|-------|-----------|
| **6.1 Branding** | *[Pendiente - WFP, BID, o propio]* |
| **6.2 Mención al BID** | *[Pendiente]* |
| **6.3 Campañas de comunicación** | *[Pendiente]* |
| **6.4 Newsletter** | *[Pendiente]* |

---

## 7. Sostenibilidad

| Campo | Respuesta |
|-------|-----------|
| **7.1 CI/CD Pipeline** | OpenShift pipelines para deployment automático desde GitHub |
| **7.2 Consultoría de mantenimiento** | *[Pendiente]* |
| **7.3 Contrato de mantenimiento** | *[Pendiente]* |
| **7.4 Equipo soporte técnico** | *[Pendiente]* |
| **7.5 Documentación técnica** | Sí - README en repositorio, documentación de APIs |
| **7.6 Documentación no técnica** | *[Pendiente]* |
| **7.7 Método de pago** | *[Pendiente]* |

---

## 8. Aspectos Legales

| Campo | Respuesta |
|-------|-----------|
| **8.1 Términos de uso** | *[Pendiente - Contactar Legal]* |
| **8.2 Recopilación actividad usuario** | No se utiliza Google Analytics ni cookies de tracking |
| **8.3 Licencias recursos gráficos** | *[Pendiente - Verificar]* |

---

## 9. Información Adicional

### 9.1 Estadísticas del Sistema

```
RESUMEN BASE DE DATOS (actualizado 2026-01-14):
================================================

Total de bases de datos: 14
Schemas activos: 6
Tablas totales: 79
Vistas SQL: 5
Registros totales: ~3,677,541

DESGLOSE POR SCHEMA:
├── idb (principal): 44 tablas, 5 vistas, ~1,990,697 registros
├── rtm_raw: 15 tablas, ~752,980 registros
├── rtm_clean: 12 tablas, ~404,338 registros
├── rtm_analytics: 6 tablas, ~529,499 registros
├── rbp: 1 tabla, ~17 registros
└── caricom_other_data: 1 tabla, ~10 registros

COBERTURA GEOGRÁFICA:
├── Países habilitados: 9
│   BLZ (Belice), BOL (Bolivia), DOM (Rep. Dominicana),
│   ECU (Ecuador), GTM (Guatemala), HND (Honduras),
│   HTI (Haití), NIC (Nicaragua), SLV (El Salvador)
│
└── Regiones (adm1): 540 divisiones administrativas

INDICADORES PRINCIPALES:
├── Food Consumption Score (FCS): ~242,615 registros
├── Reduced Coping Strategy Index (rCSI): ~248,364 registros
├── Conflictos ACLED: 68,111 eventos
├── Alertas HungerMap: 68,909 registros
└── Datos migración: 56,221 registros
```

### 9.2 Estado de Salud del Sistema

```
ESTADO ACTUALIZACIÓN DATOS (2026-01-14):
========================================

🟢 Actualizados (≤7 días): 12 tablas
   - RBP_fcs, RBP_rcsi (Food Security)
   - RBP_ACLED_conflict (Conflictos)
   - RBP_PDC_hazard (Amenazas)
   - Todas las alertas de trigger

🟡 Recientes (8-30 días): 1 tabla
   - RBP_food_inflation

🔴 Desactualizados (>90 días): 6 tablas
   - RBP_climate_anomaly
   - RBP_adm1_hml_alert
   - Datos migración

⛔ CRÍTICOS (>365 días): 8 tablas
   - RBP_ADAM_cyclon, RBP_ADAM_earthquake, RBP_ADAM_flood
   - RBP_currency_exchange
   - RBP_ipc_adm0, RBP_pou
   - RBP_population

⚠️ ISSUES CONOCIDOS:
   - ADAM API: Errores DNS (problema infraestructura)
   - BLZ, ECU: Habilitados pero sin triggers ejecutados
   - 2 tablas no existen: RBP_fcs_low_quality, RBP_rcsi_low_quality
```

### 9.3 Repositorios

| Repositorio | URL | Descripción |
|-------------|-----|-------------|
| RBP_IDB | github.com/wfp-rbp/RBP_IDB | Backend principal |
| CARICOM_platform | github.com/wfp-rbp/CARICOM_platform | Dashboard Caribbean |

---

## Nota de Confidencialidad

Este documento es confidencial y está destinado exclusivamente al equipo técnico responsable del desarrollo, implementación y mantenimiento de la solución digital descrita, así como a la contraparte técnica del Banco. Contiene información sensible relacionada con la arquitectura, seguridad y operación interna del sistema, cuya divulgación no autorizada podría comprometer su integridad, disponibilidad o confidencialidad.

---

*Documento generado: 2026-01-14*
*Versión: 2.0*
*Fuente de datos: Base de datos IDB DEV*
