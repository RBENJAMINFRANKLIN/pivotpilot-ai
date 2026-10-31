export type Session = {
  kind: "guest" | "user";
  workspace_id: string;
  user_email: string | null;
  display_name: string | null;
  expires_at: string | null;
  retention_notice: string;
  limits: Record<string, number>;
};

export type PublicConfig = {
  auth_mode: "local" | "supabase";
  guest_retention_days: number;
  ai_provider: string;
  demo_mode_enabled: boolean;
  resume_sent_to_hosted_ai: boolean;
};

export type Transition = {
  id: string;
  title: string;
  target_role: string;
  current_role: string | null;
  current_industry: string | null;
  employment_status: string | null;
  target_location: string | null;
  deadline: string | null;
  weekly_hours: number;
  study_days_per_week: number;
  budget_amount: number | null;
  budget_currency: string;
  learning_formats: string[];
  language: string;
  is_active: boolean;
  archived_at: string | null;
  version: number;
};

export type ResumeSkill = { skill_id: string; name: string; evidence: { excerpt: string; context: string }[] };
export type Resume = {
  id: string;
  version_number: number;
  source: string;
  filename: string | null;
  extraction_method: string;
  is_user_edited: boolean;
  parent_version_id: string | null;
  created_at: string;
  text_content?: string;
  extracted?: {
    sections: string[];
    experiences: { title: string; organization: string | null; start: string | null; end: string | null; bullets: string[] }[];
    education: string[];
    certifications: string[];
    skills: ResumeSkill[];
    total_years_experience: number | null;
    word_count: number;
  };
};

export type Requirement = {
  id: string;
  label: string;
  category: string;
  importance: "mandatory" | "preferred";
  skill_id: string | null;
  source_excerpt: string | null;
  source_url: string | null;
  confidence: number;
  min_years: number | null;
  prerequisite_skill_ids: string[];
};
export type Job = {
  id: string;
  source_type: string;
  source_url: string | null;
  title: string | null;
  company: string | null;
  analysis_method: string | null;
  created_at: string;
  requirements: Requirement[];
};

export type QualityComponent = { id: string; label: string; points: number; max: number; detail: string; suggestion: string | null };
export type EvidenceItem = {
  requirement_id: string;
  label: string;
  category: string;
  importance: string;
  skill_id: string | null;
  job_excerpt: string | null;
  resume_excerpts: string[];
  status: string;
  strength: number | null;
  note: string | null;
};
export type Analysis = {
  id: string;
  quality_score: number;
  quality_breakdown: { components: QualityComponent[] };
  fit_score: number | null;
  fit_breakdown: { caveat?: string; coverage?: Record<string, { count: number; with_evidence: number }>; method?: string };
  requirement_evidence: EvidenceItem[];
  transferable_skills: { skill_id: string; label: string; excerpt: string; reason: string }[];
  suggestions: { type: string; text: string }[];
  experience_alignment: { score: number | null; status: string; required_years: number | null; resume_years: number | null; note: string };
  scoring_version: string;
  created_at: string;
};

export type GapItem = {
  skill_id: string;
  name: string;
  category: string;
  importance: string;
  job_excerpt: string | null;
  current: number;
  basis: "assessed" | "provisional";
  confidence: string;
  level: string;
  target: number;
  gap: number;
  assessed_status: string;
};
export type Gaps = { status: string; items: GapItem[]; note?: string };

export type Readiness = {
  overall: number | null;
  components: Record<string, { score: number; coverage?: string; count?: number }>;
  weights: Record<string, number>;
  missing_components: string[];
  provisional: boolean;
  caveat: string;
  scoring_version: string;
};

export type Question = {
  id: string;
  skill_id: string;
  skill_name: string;
  topic: string;
  difficulty: number;
  type: string;
  prompt: string;
  code: string | null;
  choices: string[];
  select_multiple: boolean;
  free_text: boolean;
};
export type SkillResult = {
  name: string;
  importance: string;
  score: number | null;
  level: string;
  confidence: string;
  answered: number;
  accuracy: number | null;
  difficulty: Record<string, { asked: number; correct: number }>;
  highest_difficulty: number;
};
export type Attempt = {
  id: string;
  kind: string;
  status: string;
  timed: boolean;
  seconds_per_question: number | null;
  time_left: number | null;
  question: Question | null;
  progress: { skills_covered: number; skills_total: number; mandatory_complete: boolean; mandatory_missing: string[]; answered: number; budget: number };
  blueprint: { items: { skill_id: string; name: string; importance: string; min_questions: number }[]; uncovered: { skill_id: string; name: string; reason: string }[]; budget: number };
  results: null | {
    skills: Record<string, SkillResult>;
    overall: { answered: number; correct: number; accuracy: number | null };
    coverage: { mandatory_complete: boolean };
    uncovered: { name: string; reason: string }[];
    disclaimer: string;
    plan_revision?: { version: number; reasons: string[] } | null;
  };
};

export type Task = {
  id: string;
  week: number;
  day: number;
  date: string;
  skill_id: string | null;
  type: string;
  title: string;
  description: string;
  minutes: number;
  status: string;
  criteria: string;
  rationale: string;
  project_id: string | null;
  version: number;
  carried_over: boolean;
  resource: { title: string; url: string; provider: string; verification_status: string } | null;
};
export type Plan = {
  plan_id: string;
  plan_status: string;
  version_id: string;
  version: number;
  status: "provisional" | "final";
  reason: string;
  start_date: string;
  summary: {
    scope: string;
    total_hours: number;
    status_note: string;
    target_outcomes: string[];
    skills: { skill_id: string; name: string; importance: string; initial: number; basis: string; target: number; gap: number; minutes: number; resource: string | null }[];
    professional_skills: { name: string; how: string }[];
  };
  weeks: { week: number; start_date: string; planned_minutes: number; capacity_minutes: number; objectives: string[] }[];
  feasibility: {
    conflict: boolean;
    message?: string;
    weeks_needed: number;
    weeks_available?: number;
    end_date: string;
    deadline: string | null;
    total_minutes: number;
    weekly_capacity_minutes: number;
    alternatives: { type: string; text: string; deadline?: string; weekly_hours?: number; scope?: string; fits?: boolean }[];
  };
  progress: { completed_minutes: number; total_minutes: number; percent: number };
  tasks: Task[];
  versions?: { id: string; version: number; status: string; reason: string; created_at: string }[];
};

export type ResourceItem = {
  id: string;
  title: string;
  provider: string;
  url: string;
  type: string;
  level: string;
  cost_type: string;
  price: number | null;
  currency: string | null;
  duration_minutes: number | null;
  formats: string[];
  verification_status: string;
  last_checked_at: string | null;
  rationale?: string;
  rank?: number;
  source: string;
};

export type Project = {
  id: string;
  title: string;
  problem_statement: string;
  required_skills: string[];
  milestones: { title: string; done: boolean }[];
  deliverables: string[];
  rubric: { id: string; name: string; description: string }[];
  resume_evidence: string;
  rationale: string;
  status: string;
  repo_url: string | null;
  evidence: { id: string; kind: string; content: string | null; url: string | null; score: number | null; created_at: string }[];
};

export type Interview = {
  id: string;
  role: string;
  status: string;
  overall_score: number | null;
  rubric: { id: string; name: string; description: string }[];
  questions: {
    id: string;
    text: string;
    type: string;
    competency: string;
    answer: string | null;
    overall: number | null;
    criteria: Record<string, number> | null;
    method: string | null;
    feedback: { strengths: string[]; improvements: string[]; outline: string[] } | null;
  }[];
};

export type Application = {
  id: string;
  company: string;
  role_title: string;
  role_category: string;
  company_size: string;
  source: string;
  url: string | null;
  status: string;
  applied_at: string | null;
  interview_dates: string[];
  notes: string | null;
  version: number;
  history: { from: string | null; to: string; note: string | null; at: string }[];
};
