"""Skill taxonomy: canonical skills, aliases used for matching, prerequisites and
rough learning effort (hours from novice to working proficiency; heuristic, used only
to size learning plans, and shown to users as an estimate)."""

# id, name, category, learn_hours, aliases, prerequisites, related (partial transfer)
SKILLS: list[dict] = [
    # data
    dict(id="sql", name="SQL", category="technical", hours=40,
         aliases=["sql", "postgresql", "postgres", "mysql", "t-sql", "sqlite", "sql queries", "structured query language", "bigquery", "snowflake"],
         prereqs=[], related=["excel", "data-analysis"]),
    dict(id="excel", name="Spreadsheets (Excel / Google Sheets)", category="tool", hours=25,
         aliases=["excel", "microsoft excel", "ms excel", "spreadsheets", "spreadsheet", "google sheets", "pivot tables", "pivot table", "vlookup", "xlookup"],
         prereqs=[], related=["data-analysis"]),
    dict(id="statistics", name="Statistics", category="technical", hours=50,
         aliases=["statistics", "statistical analysis", "hypothesis testing", "a/b testing", "ab testing", "regression analysis", "probability", "inferential statistics", "descriptive statistics"],
         prereqs=[], related=["data-analysis"]),
    dict(id="python", name="Python", category="technical", hours=50,
         aliases=["python", "python3", "python 3"], prereqs=[], related=["javascript"]),
    dict(id="pandas", name="pandas", category="tool", hours=25,
         aliases=["pandas", "dataframes", "dataframe", "numpy"], prereqs=["python"], related=["excel", "sql"]),
    dict(id="data-visualization", name="Data visualization", category="technical", hours=25,
         aliases=["data visualization", "data visualisation", "dashboards", "dashboard", "dashboarding", "matplotlib", "seaborn", "plotly", "looker studio", "data storytelling"],
         prereqs=[], related=["excel"]),
    dict(id="data-cleaning", name="Data cleaning", category="technical", hours=20,
         aliases=["data cleaning", "data cleansing", "data wrangling", "data preparation", "data quality", "data validation"],
         prereqs=[], related=["excel"]),
    dict(id="data-analysis", name="Data analysis", category="technical", hours=30,
         aliases=["data analysis", "data analytics", "exploratory data analysis", "analytical skills", "analyze data", "analyse data", "eda"],
         prereqs=[], related=["excel", "statistics"]),
    dict(id="tableau", name="Tableau", category="tool", hours=20, aliases=["tableau"], prereqs=["data-visualization"], related=["power-bi"]),
    dict(id="power-bi", name="Power BI", category="tool", hours=20, aliases=["power bi", "powerbi", "dax"], prereqs=["data-visualization"], related=["tableau", "excel"]),
    dict(id="machine-learning", name="Machine learning", category="technical", hours=80,
         aliases=["machine learning", "scikit-learn", "sklearn", "predictive modeling", "predictive modelling"],
         prereqs=["python", "statistics"], related=[]),
    dict(id="r-lang", name="R", category="technical", hours=45, aliases=["r programming", "rstudio", "tidyverse", "ggplot2"], prereqs=[], related=["python"]),
    # software
    dict(id="javascript", name="JavaScript", category="technical", hours=50, aliases=["javascript", "js", "es6", "ecmascript"], prereqs=[], related=["python"]),
    dict(id="typescript", name="TypeScript", category="technical", hours=20, aliases=["typescript"], prereqs=["javascript"], related=[]),
    dict(id="html-css", name="HTML & CSS", category="technical", hours=25, aliases=["html", "css", "html5", "css3", "tailwind", "responsive design"], prereqs=[], related=[]),
    dict(id="react", name="React", category="tool", hours=35, aliases=["react", "react.js", "reactjs"], prereqs=["javascript", "html-css"], related=[]),
    dict(id="nodejs", name="Node.js", category="tool", hours=30, aliases=["node.js", "nodejs", "express.js"], prereqs=["javascript"], related=[]),
    dict(id="git", name="Git & version control", category="tool", hours=10, aliases=["git", "github", "gitlab", "version control"], prereqs=[], related=[]),
    dict(id="rest-apis", name="REST APIs & HTTP", category="technical", hours=20, aliases=["rest api", "rest apis", "restful", "api design", "apis", "web services"], prereqs=[], related=[]),
    dict(id="software-testing", name="Software testing", category="technical", hours=20, aliases=["unit testing", "software testing", "test automation", "pytest", "jest", "qa testing"], prereqs=[], related=[]),
    dict(id="cloud", name="Cloud platforms", category="tool", hours=40, aliases=["aws", "azure", "gcp", "google cloud", "cloud computing"], prereqs=[], related=[]),
    dict(id="docker", name="Docker & containers", category="tool", hours=15, aliases=["docker", "containers", "kubernetes", "containerization"], prereqs=["linux"], related=[]),
    dict(id="linux", name="Linux & command line", category="tool", hours=15, aliases=["linux", "bash", "command line", "shell scripting", "unix"], prereqs=[], related=[]),
    # product & design
    dict(id="product-management", name="Product management", category="technical", hours=40,
         aliases=["product management", "product roadmap", "roadmapping", "product strategy", "prioritization", "prioritisation", "product requirements", "prd"],
         prereqs=[], related=["project-management"]),
    dict(id="agile", name="Agile & Scrum", category="professional", hours=12, aliases=["agile", "scrum", "kanban", "sprint planning", "jira"], prereqs=[], related=["project-management"]),
    dict(id="user-research", name="User research", category="technical", hours=25,
         aliases=["user research", "ux research", "usability testing", "user interviews", "customer interviews", "user testing"],
         prereqs=[], related=["communication"]),
    dict(id="ux-design", name="UX design", category="technical", hours=40, aliases=["ux design", "user experience", "wireframing", "wireframes", "prototyping", "interaction design"], prereqs=["user-research"], related=[]),
    dict(id="figma", name="Figma", category="tool", hours=10, aliases=["figma"], prereqs=[], related=[]),
    dict(id="project-management", name="Project management", category="professional", hours=25,
         aliases=["project management", "project planning", "pmp", "program management", "managed projects", "project coordination"], prereqs=[], related=["agile"]),
    dict(id="instructional-design", name="Instructional design", category="domain", hours=30,
         aliases=["instructional design", "curriculum design", "curriculum development", "lesson planning", "e-learning", "learning design"], prereqs=[], related=["communication"]),
    dict(id="digital-marketing", name="Digital marketing", category="domain", hours=30, aliases=["digital marketing", "seo", "sem", "google analytics", "marketing analytics", "email marketing"], prereqs=[], related=[]),
    dict(id="financial-analysis", name="Financial analysis", category="domain", hours=40, aliases=["financial analysis", "financial modeling", "financial modelling", "budgeting", "forecasting"], prereqs=["excel"], related=[]),
    dict(id="customer-service", name="Customer service", category="professional", hours=10, aliases=["customer service", "customer support", "client relations", "customer success"], prereqs=[], related=["communication"]),
    # professional competencies
    dict(id="communication", name="Communication & presentation", category="professional", hours=15,
         aliases=["communication", "communication skills", "presentation", "presentations", "presenting", "public speaking", "written communication", "storytelling"], prereqs=[], related=[]),
    dict(id="stakeholder-management", name="Stakeholder management", category="professional", hours=15,
         aliases=["stakeholder management", "stakeholders", "cross-functional", "cross functional", "parent communication"], prereqs=[], related=["communication"]),
    dict(id="leadership", name="Leadership & mentoring", category="professional", hours=20, aliases=["leadership", "mentoring", "coaching", "team lead", "led a team"], prereqs=[], related=[]),
    dict(id="problem-solving", name="Problem solving", category="professional", hours=10, aliases=["problem solving", "problem-solving", "critical thinking", "troubleshooting"], prereqs=[], related=[]),
    dict(id="collaboration", name="Collaboration", category="professional", hours=8, aliases=["collaboration", "teamwork", "collaborated", "team player"], prereqs=[], related=[]),
]

# Role families: which skills a target role usually needs when no job description is supplied.
# Used only as an explicit "role template" (labelled as such in the UI), never as extracted facts.
ROLE_TEMPLATES: dict[str, dict] = {
    "data analyst": {
        "mandatory": ["sql", "excel", "data-analysis", "data-visualization", "statistics", "communication"],
        "preferred": ["python", "pandas", "tableau", "power-bi", "data-cleaning", "stakeholder-management"],
        "family": "data",
    },
    "business analyst": {
        "mandatory": ["excel", "sql", "data-analysis", "stakeholder-management", "communication"],
        "preferred": ["data-visualization", "power-bi", "agile", "project-management"],
        "family": "data",
    },
    "data scientist": {
        "mandatory": ["python", "statistics", "machine-learning", "sql", "pandas"],
        "preferred": ["data-visualization", "cloud", "communication", "git"],
        "family": "data",
    },
    "software engineer": {
        "mandatory": ["javascript", "git", "rest-apis", "software-testing", "problem-solving"],
        "preferred": ["typescript", "react", "nodejs", "python", "cloud", "docker", "sql"],
        "family": "software",
    },
    "frontend developer": {
        "mandatory": ["javascript", "html-css", "react", "git"],
        "preferred": ["typescript", "rest-apis", "software-testing", "figma"],
        "family": "software",
    },
    "product manager": {
        "mandatory": ["product-management", "stakeholder-management", "communication", "agile", "data-analysis"],
        "preferred": ["user-research", "sql", "project-management"],
        "family": "product",
    },
    "ux designer": {
        "mandatory": ["ux-design", "user-research", "figma", "communication"],
        "preferred": ["html-css", "collaboration", "stakeholder-management"],
        "family": "design",
    },
    "instructional designer": {
        "mandatory": ["instructional-design", "communication", "project-management"],
        "preferred": ["user-research", "stakeholder-management", "data-analysis"],
        "family": "learning",
    },
    "project manager": {
        "mandatory": ["project-management", "stakeholder-management", "communication", "agile"],
        "preferred": ["excel", "leadership", "problem-solving"],
        "family": "product",
    },
}


def role_family(target_role: str) -> str:
    t = target_role.lower()
    for key, tpl in ROLE_TEMPLATES.items():
        if key in t:
            return tpl["family"]
    if any(w in t for w in ("data", "analyst", "analytics", "bi ")):
        return "data"
    if any(w in t for w in ("engineer", "developer", "programmer")):
        return "software"
    if any(w in t for w in ("product", "project", "program")):
        return "product"
    if any(w in t for w in ("design", "ux", "ui")):
        return "design"
    return "general"


def role_template(target_role: str) -> dict | None:
    t = target_role.lower()
    for key, tpl in ROLE_TEMPLATES.items():
        if key in t:
            return tpl
    return None
