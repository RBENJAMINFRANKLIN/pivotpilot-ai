"""Curated resource catalogue.

Only well-known canonical URLs are listed. Prices, durations, ratings and instructors are
deliberately NOT recorded here: they change and must not be invented. Cost type is
recorded only where the provider publishes the material free of charge or is known to
charge (Coursera certificates are subscription-based; auditing options vary).
Every entry starts as `unverified` until the verification job checks the URL.
"""


def r(title, provider, url, rtype, skills, *, cost="free", level="beginner", prereqs=(), formats=("reading",), desc=""):
    return dict(title=title, provider=provider, canonical_url=url, resource_type=rtype, skills=list(skills),
                cost_type=cost, level=level, prerequisites=list(prereqs), formats=list(formats), description=desc)


RESOURCES: list[dict] = [
    # SQL
    r("SQLBolt - Learn SQL with simple, interactive exercises", "SQLBolt", "https://sqlbolt.com/", "practice", ["sql"],
      formats=("interactive", "reading"), desc="Short interactive lessons covering SELECT, joins and aggregates."),
    r("Kaggle Learn: Intro to SQL", "Kaggle", "https://www.kaggle.com/learn/intro-to-sql", "course", ["sql"],
      formats=("interactive",), desc="Hands-on SQL notebooks using BigQuery public datasets."),
    r("Kaggle Learn: Advanced SQL", "Kaggle", "https://www.kaggle.com/learn/advanced-sql", "course", ["sql"],
      level="intermediate", prereqs=("sql",), formats=("interactive",), desc="Joins, window functions and query efficiency."),
    r("PostgreSQL Tutorial (official documentation)", "PostgreSQL Global Development Group",
      "https://www.postgresql.org/docs/current/tutorial.html", "docs", ["sql"], desc="The official introductory tutorial."),
    r("Khan Academy: Intro to SQL", "Khan Academy", "https://www.khanacademy.org/computing/computer-programming/sql", "course", ["sql"],
      formats=("video", "interactive"), desc="Beginner-friendly SQL with in-browser challenges."),
    # Spreadsheets
    r("Excel help & learning", "Microsoft", "https://support.microsoft.com/en-us/excel", "docs", ["excel"],
      formats=("reading", "video"), desc="Official Excel training and function reference."),
    r("Google Docs Editors Help (Sheets)", "Google", "https://support.google.com/docs/", "docs", ["excel"],
      formats=("reading",), desc="Official help centre for Google Sheets and the other Docs editors."),
    # Statistics
    r("Khan Academy: Statistics and probability", "Khan Academy", "https://www.khanacademy.org/math/statistics-probability",
      "course", ["statistics"], formats=("video", "interactive"), desc="Full introductory statistics course."),
    r("OpenIntro Statistics (free textbook)", "OpenIntro", "https://www.openintro.org/book/os/", "book", ["statistics"],
      level="intermediate", desc="Free, widely used introductory statistics textbook."),
    r("MIT 18.05 Introduction to Probability and Statistics", "MIT OpenCourseWare",
      "https://ocw.mit.edu/courses/18-05-introduction-to-probability-and-statistics-spring-2014/", "course", ["statistics"],
      level="intermediate", formats=("reading", "video"), desc="University course materials, problem sets and exams."),
    # Python
    r("The Python Tutorial (official)", "Python Software Foundation", "https://docs.python.org/3/tutorial/", "docs", ["python"],
      desc="The official introduction to the Python language."),
    r("Kaggle Learn: Python", "Kaggle", "https://www.kaggle.com/learn/python", "course", ["python"], formats=("interactive",)),
    r("CS50's Introduction to Programming with Python", "Harvard University", "https://cs50.harvard.edu/python/", "course", ["python"],
      formats=("video", "practice"), desc="Lectures and problem sets; free to follow online."),
    r("MIT 6.0001 Introduction to Computer Science and Programming in Python", "MIT OpenCourseWare",
      "https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/", "course",
      ["python", "problem-solving"], formats=("video", "reading"), level="intermediate"),
    # pandas / data analysis
    r("pandas: Getting started tutorials", "pandas", "https://pandas.pydata.org/docs/getting_started/intro_tutorials/index.html",
      "docs", ["pandas", "data-cleaning"], prereqs=("python",)),
    r("Kaggle Learn: Pandas", "Kaggle", "https://www.kaggle.com/learn/pandas", "course", ["pandas"], prereqs=("python",), formats=("interactive",)),
    r("Kaggle Learn: Data Cleaning", "Kaggle", "https://www.kaggle.com/learn/data-cleaning", "course", ["data-cleaning", "pandas"],
      prereqs=("pandas",), formats=("interactive",), level="intermediate"),
    r("Google Data Analytics Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-data-analytics",
      "course", ["data-analysis", "sql", "excel", "data-visualization", "data-cleaning", "tableau", "r-lang"], cost="subscription",
      formats=("video", "practice"), desc="Paid certificate programme; Coursera may offer financial aid or audit options."),
    # Visualization / BI
    r("Kaggle Learn: Data Visualization", "Kaggle", "https://www.kaggle.com/learn/data-visualization", "course", ["data-visualization"],
      prereqs=("python",), formats=("interactive",)),
    r("Fundamentals of Data Visualization (free online book)", "Claus O. Wilke", "https://clauswilke.com/dataviz/", "book",
      ["data-visualization"], level="intermediate"),
    r("Tableau free training videos", "Tableau", "https://www.tableau.com/learn/training", "course", ["tableau", "data-visualization"],
      formats=("video",)),
    r("Power BI training on Microsoft Learn", "Microsoft", "https://learn.microsoft.com/en-us/training/powerplatform/power-bi",
      "course", ["power-bi", "data-visualization"], formats=("reading", "interactive")),
    # Machine learning
    r("Kaggle Learn: Intro to Machine Learning", "Kaggle", "https://www.kaggle.com/learn/intro-to-machine-learning", "course",
      ["machine-learning"], prereqs=("python",), formats=("interactive",)),
    r("scikit-learn User Guide", "scikit-learn", "https://scikit-learn.org/stable/user_guide.html", "docs", ["machine-learning"],
      prereqs=("python", "statistics"), level="intermediate"),
    r("Machine Learning Specialization", "Coursera", "https://www.coursera.org/specializations/machine-learning-introduction",
      "course", ["machine-learning"], cost="subscription", formats=("video", "practice"), prereqs=("python",)),
    # Web / software
    r("MDN JavaScript Guide", "MDN Web Docs", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide", "docs", ["javascript"]),
    r("The Modern JavaScript Tutorial", "javascript.info", "https://javascript.info/", "tutorial", ["javascript"]),
    r("MDN Learn web development", "MDN Web Docs", "https://developer.mozilla.org/en-US/docs/Learn", "course", ["html-css", "javascript"],
      formats=("reading", "practice")),
    r("freeCodeCamp curriculum", "freeCodeCamp", "https://www.freecodecamp.org/learn/", "course", ["html-css", "javascript"],
      formats=("interactive", "practice")),
    r("TypeScript Handbook", "Microsoft", "https://www.typescriptlang.org/docs/handbook/intro.html", "docs", ["typescript"], prereqs=("javascript",)),
    r("React: Quick Start (official docs)", "React", "https://react.dev/learn", "docs", ["react"], prereqs=("javascript", "html-css")),
    r("Pro Git book", "Git", "https://git-scm.com/book/en/v2", "book", ["git"], desc="The official Git book, free online."),
    r("MDN: An overview of HTTP", "MDN Web Docs", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview", "docs", ["rest-apis"]),
    r("CS50x: Introduction to Computer Science", "Harvard University", "https://cs50.harvard.edu/x/", "course",
      ["problem-solving", "python", "sql", "html-css"], formats=("video", "practice")),
    r("Node.js: Learn", "OpenJS Foundation", "https://nodejs.org/en/learn", "docs", ["nodejs"], prereqs=("javascript",)),
    r("Docker: Get started", "Docker", "https://docs.docker.com/get-started/", "docs", ["docker"], prereqs=("linux",)),
    # Product / agile / research / design
    r("The Scrum Guide", "Scrum.org / Scrum Inc.", "https://scrumguides.org/scrum-guide.html", "docs", ["agile"]),
    r("Nielsen Norman Group articles", "Nielsen Norman Group", "https://www.nngroup.com/articles/", "docs", ["user-research", "ux-design"],
      level="intermediate"),
    r("Google UX Design Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-ux-design",
      "course", ["ux-design", "user-research", "figma"], cost="subscription", formats=("video", "practice")),
    r("Figma Learn", "Figma", "https://help.figma.com/hc/en-us", "docs", ["figma"]),
    r("Google Project Management Professional Certificate", "Coursera",
      "https://www.coursera.org/professional-certificates/google-project-management", "course", ["project-management", "agile"],
      cost="subscription", formats=("video", "practice")),
]
