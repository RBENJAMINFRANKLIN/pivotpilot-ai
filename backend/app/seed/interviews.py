"""Mock-interview question bank and the stable scoring rubric (version interview-rubric-v1).

Each criterion is scored 1-5. The rubric is the same for every evaluation method; only
the evaluator differs (LLM with schema-validated output, or the transparent heuristic)."""

RUBRIC_VERSION = "interview-rubric-v1"

RUBRIC = [
    {"id": "relevance", "name": "Relevance", "description": "Answers the question that was asked, for this role."},
    {"id": "structure", "name": "Structure", "description": "Clear order; for behavioural questions, Situation-Task-Action-Result."},
    {"id": "evidence", "name": "Specific evidence", "description": "Concrete examples, numbers or outcomes from the candidate's own experience."},
    {"id": "depth", "name": "Depth", "description": "Shows understanding of trade-offs, reasoning or technical detail."},
    {"id": "communication", "name": "Communication", "description": "Concise, plain language, appropriate length."},
]

# family: general applies to every role; competencies map to skill ids where relevant
QUESTIONS = [
    dict(id="gen-why", family="general", type="behavioral", competency="motivation",
         text="Why are you moving into this role, and what have you done so far to prepare?"),
    dict(id="gen-conflict", family="general", type="behavioral", competency="stakeholder-management",
         text="Tell me about a time you disagreed with a colleague or stakeholder. What did you do and what was the result?"),
    dict(id="gen-learn", family="general", type="behavioral", competency="problem-solving",
         text="Describe a time you had to learn something new quickly to get a job done."),
    dict(id="gen-failure", family="general", type="behavioral", competency="collaboration",
         text="Tell me about a project that did not go as planned. What did you learn?"),
    dict(id="gen-priorities", family="general", type="scenario", competency="project-management",
         text="You have three urgent requests from different people and time for one. How do you decide what to do?"),
    dict(id="data-sql", family="data", type="technical", competency="sql",
         text="Explain how you would find the top 3 products by revenue in each region using SQL."),
    dict(id="data-clean", family="data", type="technical", competency="data-cleaning",
         text="You receive a messy spreadsheet of customer orders. Walk me through how you would clean it before analysis."),
    dict(id="data-stakeholder", family="data", type="scenario", competency="communication",
         text="A manager asks why sales dropped last month. How would you investigate and present your findings?"),
    dict(id="data-ab", family="data", type="technical", competency="statistics",
         text="How would you decide whether an A/B test result is trustworthy?"),
    dict(id="data-viz", family="data", type="technical", competency="data-visualization",
         text="How do you choose the right chart for a dashboard, and how do you avoid misleading viewers?"),
    dict(id="sw-debug", family="software", type="technical", competency="problem-solving",
         text="Walk me through how you would debug a web page that works locally but fails in production."),
    dict(id="sw-api", family="software", type="technical", competency="rest-apis",
         text="How would you design a REST API for a simple to-do application? Name the endpoints and status codes."),
    dict(id="sw-testing", family="software", type="technical", competency="software-testing",
         text="What would you test in a function that calculates shipping costs, and why?"),
    dict(id="sw-review", family="software", type="scenario", competency="collaboration",
         text="A reviewer leaves many critical comments on your pull request. How do you respond?"),
    dict(id="pm-prioritize", family="product", type="scenario", competency="product-management",
         text="You have ten feature requests and capacity for two. How do you decide?"),
    dict(id="pm-metric", family="product", type="technical", competency="data-analysis",
         text="What metrics would you track for a new onboarding flow, and how would you know it is working?"),
    dict(id="pm-discovery", family="product", type="behavioral", competency="user-research",
         text="Tell me about a time you used customer feedback to change a plan."),
    dict(id="ux-research", family="design", type="technical", competency="user-research",
         text="How would you plan research to understand why users abandon a sign-up form?"),
    dict(id="ux-critique", family="design", type="scenario", competency="ux-design",
         text="A stakeholder dislikes your design but cannot say why. What do you do?"),
    dict(id="ld-design", family="learning", type="technical", competency="instructional-design",
         text="How would you design a short online course for new employees, and how would you measure whether it works?"),
]
