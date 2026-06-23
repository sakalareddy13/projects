## AI Cloud Cost Detective - Architecture (AWS Edition)

```
                              ┌──────────────┐
                              │     USER     │
                              └──────┬───────┘
                                     │
                                     ▼
                           ┌───────────────────┐
                           │  REACT FRONTEND   │
                           └────────┬──────────┘
                                    :
                                    : Login / Signup
                                    ▼
                           ┌───────────────────┐
                           │  PYTHON BACKEND   │
                           │    (FastAPI)      │
                           │                   │
                           │  · Custom JWT Auth│
                           └───┬───────┬───┬───┘
                               :       :   :
                ┌──────────────┘       :   └──────────────┐
                :                      :                  :
                ▼                      ▼                  ▼
         ┌─────────────┐     ┌──────────────┐    ┌──────────────┐
         │  AWS SDK    │     │   FASTAPI    │    │   OPENAI     │
         │  (boto3)    │     │  WEBSOCKET   │    │    API       │
         │             │     │  (Progress)  │    │              │
         │ describe    │     └──────┬───────┘    │ Cost Analysis│
         │ _instances  │            :            └──────┬───────┘
         └──────┬──────┘            : Live updates      :
                :                   ▼                   :
                ▼           ┌───────────────┐            :
         ┌─────────────┐   │    REACT      │            :
         │   AWS EC2   │   │  (Progress    │            :
         │   + RDS     │   │   Tracker)    │            :
         │   + S3      │   └───────────────┘            :
         │   + Others  │                                :
         └─────────────┘                                ▼
                                                 ┌──────────────┐
                                                 │    AWS RDS   │
                                                 │  PostgreSQL  │
                                                 │  (Managed)   │
                                                 │              │
                                                 │ · users      │
                                                 │ · analyses   │
                                                 └──────┬───────┘
                                                        :
                                                        : Stored results
                                                        ▼
                                                 ┌───────────────┐
                                                 │    REACT      │
                                                 │ (Final Report │
                                                 │  + Suggestions│
                                                 │  + Fixes)     │
                                                 └───────────────┘
```
