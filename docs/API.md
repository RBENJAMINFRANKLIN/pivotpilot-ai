# API reference

Interactive OpenAPI docs: **http://localhost:8000/api/docs** (JSON: `/api/openapi.json`). All endpoints are under `/api/v1`, need a session (guest cookie, auth cookie or `Authorization: Bearer`) except `/config`, `/session`, `/session/guest`, `/auth/*` and `/demo/start`, and state-changing requests need the header `X-PivotPilot-Client: web` (or a Bearer token).

Errors: `{"detail": {"code": "STABLE_CODE", "message": "Plain explanation"}}`.

| Method | Path | Area | Summary |
|---|---|---|---|
| `GET` | `/health` | health | Health |
| `GET` | `/health/ready` | health | Ready |
| `GET` | `/api/v1/config` | session | Public Config |
| `GET` | `/api/v1/session` | session | Get Session |
| `POST` | `/api/v1/session/guest` | session | Start Guest |
| `POST` | `/api/v1/auth/register` | session | Register |
| `POST` | `/api/v1/auth/login` | session | Login |
| `POST` | `/api/v1/auth/logout` | session | Logout |
| `POST` | `/api/v1/auth/migrate-guest` | session | Migrate Guest |
| `DELETE` | `/api/v1/workspace` | session | Delete Everything |
| `GET` | `/api/v1/transitions` | career transitions | List Transitions |
| `POST` | `/api/v1/transitions` | career transitions | Create Transition |
| `GET` | `/api/v1/transitions/{transition_id}` | career transitions | Get Transition |
| `PATCH` | `/api/v1/transitions/{transition_id}` | career transitions | Patch Transition |
| `POST` | `/api/v1/transitions/{transition_id}/activate` | career transitions | Activate Transition |
| `POST` | `/api/v1/transitions/{transition_id}/archive` | career transitions | Archive Transition |
| `POST` | `/api/v1/transitions/{transition_id}/restore` | career transitions | Restore Transition |
| `GET` | `/api/v1/profile` | career transitions | Get Profile |
| `PUT` | `/api/v1/profile` | career transitions | Put Profile |
| `POST` | `/api/v1/resumes/upload` | resumes | Upload Resume |
| `POST` | `/api/v1/resumes/text` | resumes | Paste Resume |
| `GET` | `/api/v1/resumes` | resumes | List Resumes |
| `GET` | `/api/v1/resumes/{resume_id}` | resumes | Get Resume |
| `DELETE` | `/api/v1/resumes/{resume_id}` | resumes | Delete Resume |
| `PUT` | `/api/v1/resumes/{resume_id}/extracted` | resumes | Edit Extraction |
| `POST` | `/api/v1/transitions/{transition_id}/job` | job analysis | Set Job |
| `GET` | `/api/v1/transitions/{transition_id}/job` | job analysis | Get Job |
| `POST` | `/api/v1/transitions/{transition_id}/analysis` | job analysis | Run Analysis |
| `GET` | `/api/v1/transitions/{transition_id}/analysis` | job analysis | Get Analysis |
| `GET` | `/api/v1/transitions/{transition_id}/gaps` | job analysis | Get Gaps |
| `GET` | `/api/v1/transitions/{transition_id}/readiness` | job analysis | Get Readiness |
| `POST` | `/api/v1/transitions/{transition_id}/assessments` | assessments | Start |
| `GET` | `/api/v1/transitions/{transition_id}/assessments` | assessments | History |
| `GET` | `/api/v1/assessments/{attempt_id}` | assessments | Get Attempt |
| `POST` | `/api/v1/assessments/{attempt_id}/answer` | assessments | Submit Answer |
| `POST` | `/api/v1/assessments/{attempt_id}/finish` | assessments | Finish Attempt |
| `GET` | `/api/v1/assessments/{attempt_id}/review` | assessments | Review |
| `POST` | `/api/v1/transitions/{transition_id}/plan` | learning plan | Generate |
| `GET` | `/api/v1/transitions/{transition_id}/plan` | learning plan | Current Plan |
| `GET` | `/api/v1/plan-versions/{version_id}` | learning plan | Plan Version |
| `POST` | `/api/v1/transitions/{transition_id}/plan/pause` | learning plan | Pause |
| `POST` | `/api/v1/transitions/{transition_id}/plan/resume` | learning plan | Resume |
| `PATCH` | `/api/v1/tasks/{task_id}` | learning plan | Update Task |
| `GET` | `/api/v1/transitions/{transition_id}/resources` | learning plan | Recommendations |
| `POST` | `/api/v1/transitions/{transition_id}/resources/refresh` | learning plan | Refresh |
| `GET` | `/api/v1/resources` | learning plan | Catalogue |
| `POST` | `/api/v1/resources/{resource_id}/verify` | learning plan | Verify |
| `GET` | `/api/v1/transitions/{transition_id}/projects` | learning plan | List Projects |
| `PATCH` | `/api/v1/projects/{project_id}` | learning plan | Update Project |
| `POST` | `/api/v1/projects/{project_id}/evidence` | learning plan | Add Evidence |
| `POST` | `/api/v1/transitions/{transition_id}/interviews` | interviews & applications | Start Interview |
| `GET` | `/api/v1/transitions/{transition_id}/interviews` | interviews & applications | List Interviews |
| `GET` | `/api/v1/interviews/{interview_id}` | interviews & applications | Get Interview |
| `POST` | `/api/v1/interviews/{interview_id}/answers` | interviews & applications | Answer Interview |
| `GET` | `/api/v1/applications` | interviews & applications | List Applications |
| `POST` | `/api/v1/applications` | interviews & applications | Add Application |
| `PATCH` | `/api/v1/applications/{application_id}` | interviews & applications | Patch Application |
| `DELETE` | `/api/v1/applications/{application_id}` | interviews & applications | Delete Application |
| `GET` | `/api/v1/applications/analytics` | interviews & applications | Application Analytics |
| `POST` | `/api/v1/commands/interpret` | natural-language commands | Interpret |
| `POST` | `/api/v1/commands/execute` | natural-language commands | Execute |
| `GET` | `/api/v1/dashboard` | dashboard | Dashboard |
| `POST` | `/api/v1/demo/start` | dashboard | Start Demo |