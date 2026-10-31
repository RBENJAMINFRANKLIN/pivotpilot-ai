import { expect, test, type Page } from "@playwright/test";

const RESUME = `Jordan Rivera
jordan.rivera@example.com | +1 555 0100

Summary
Secondary school mathematics teacher with 7 years of experience, moving into data analysis.

Experience
Mathematics Teacher, Lakeside High School  Aug 2017 - Present
- Analysed termly assessment data for 180 students in Excel using pivot tables to identify learning gaps
- Built a Google Sheets dashboard tracking attendance and grades, used weekly by 6 colleagues
- Presented progress reports to parents and the leadership team each term

Education
BSc Mathematics, State University, 2015

Skills
Excel, Google Sheets, statistics, communication`;

const JOB = `Junior Data Analyst

Requirements
- Strong SQL skills are required
- Advanced Excel, including pivot tables and lookups
- Solid understanding of statistics and hypothesis testing
- Excellent communication skills
- 1+ years of experience working with data

Nice to have
- Python with pandas is a plus
- Experience with Tableau or Power BI is preferred`;

const nav = (page: Page, name: string) => page.getByRole("navigation", { name: "Main" }).getByRole("link", { name, exact: true });

function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("Failed to load resource")) errors.push(m.text()); });
  return errors;
}

test("guest completes the full journey, then saves progress to an account", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.getByText("Next recommended actions")).toBeVisible();

  // 2. create a career goal
  await nav(page, "Career goals").click();
  await page.getByLabel("Goal name").fill("Teacher to data analyst");
  await page.getByLabel("Target role").fill("Junior Data Analyst");
  await page.getByLabel("Current role").fill("Teacher");
  await page.getByRole("button", { name: "Create goal" }).click();
  await expect(page.getByText("active", { exact: true })).toBeVisible();

  // 3-5. resume, job, constraints
  await nav(page, "Resume & job").click();
  await page.getByRole("tab", { name: "Paste or dictate text" }).click();
  await page.getByLabel("Resume or career summary").fill(RESUME);
  await page.getByRole("button", { name: "Save resume" }).click();
  await expect(page.getByText("Skills found, with the line that mentions each")).toBeVisible();
  await page.getByRole("button", { name: "Job link" }).click();
  await page.getByLabel("Job posting URL").fill("https://www.linkedin.com/jobs/view/1");
  await page.getByRole("button", { name: "Extract requirements" }).click();
  await expect(page.getByText(/paste the job description/i)).toBeVisible(); // URL fallback to pasted text
  await page.getByLabel("Job description").fill(JOB);
  await page.getByRole("button", { name: "Extract requirements" }).click();
  await expect(page.getByText("Current competency map")).toBeVisible();
  await page.getByLabel("Hours per week you can study").fill("5");
  await page.getByRole("button", { name: "Save and analyse my fit" }).click();

  // 6-8. analysis with evidence
  await expect(page.getByRole("heading", { name: "Fit analysis" })).toBeVisible();
  await expect(page.getByText("Requirement by requirement")).toBeVisible();
  await expect(page.getByText(/pivot tables to identify learning gaps/).first()).toBeVisible();

  // persistence across refresh (guest)
  await page.reload();
  await expect(page.getByRole("heading", { name: "Fit analysis" })).toBeVisible();

  // 9-11. adaptive assessment
  await nav(page, "Assessment").click();
  await page.getByRole("button", { name: /^(Start|Continue assessment)$/ }).click();
  for (let i = 0; i < 40; i++) {
    await page.locator("main h2.text-lg, main h1:has-text('Your results')").first().waitFor();
    if (await page.getByRole("heading", { name: "Your results" }).isVisible()) break;
    const answerBox = page.getByLabel("Your answer");
    if (await answerBox.isVisible()) {
      await answerBox.fill("2");
      await page.getByRole("button", { name: "Submit answer" }).click();
    } else if (await page.getByText("Select all that apply.", { exact: true }).isVisible()) {
      await page.locator("button[aria-pressed]").first().click();
      await page.getByRole("button", { name: "Submit answer" }).click();
    } else {
      await page.locator("main button.rounded-xl").first().click();
    }
    await page.waitForTimeout(150);
  }
  await expect(page.getByRole("heading", { name: "Your results" })).toBeVisible();
  await expect(page.getByText(/not a validated measure/)).toBeVisible();
  await page.getByRole("button", { name: "Done" }).click();

  // 12-13. plan
  await nav(page, "Learning plan").click();
  await page.getByRole("button", { name: "Generate my plan" }).click();
  await expect(page.getByText("final", { exact: true }).first()).toBeVisible();
  const firstTask = page.getByRole("checkbox", { name: /Mark .* complete/ }).first();
  await firstTask.click();
  await expect(firstTask).toBeChecked();

  // Wispr Flow-style dictated command: interpret -> confirm -> executed
  await page.getByLabel("Tell PivotPilot what changed").fill("Um, I can study about 8 hours a week now");
  await page.getByRole("button", { name: "Interpret" }).click();
  await expect(page.getByText("Change weekly study time to 8 hours")).toBeVisible();
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText(/Done: Change weekly study time to 8 hours/)).toBeVisible();

  // 16. mock interview + applications
  await nav(page, "Mock interviews").click();
  await page.getByRole("button", { name: "Start a mock interview" }).click();
  await page.getByLabel("Your answer").first().fill("When I was teaching, my goal was to raise the pass rate. I analysed the results in Excel because I wanted to find weak topics, then I designed weekly quizzes. As a result the pass rate rose from 68% to 81%.");
  await page.getByRole("button", { name: "Get feedback" }).first().click();
  await expect(page.getByText("Strengths").first()).toBeVisible();
  await nav(page, "Applications").click();
  await page.getByLabel("Company", { exact: true }).fill("Acme");
  await page.getByLabel("Role title").fill("Junior Data Analyst");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("applied → ", { exact: false }).or(page.getByText("saved → applied"))).toBeVisible();

  // 17. dashboard shows the indicators
  await nav(page, "Dashboard").click();
  await expect(page.getByRole("heading", { name: "Assessed skills" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Learning plan" })).toBeVisible();

  // Save My Progress: guest -> account migration
  await page.getByRole("button", { name: "Save My Progress" }).click();
  await page.getByLabel("Email").fill(`e2e-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("a long test password");
  await page.getByRole("button", { name: "Create account & save progress" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await nav(page, "Career goals").click();
  await expect(page.getByText("Teacher to data analyst")).toBeVisible();

  expect(errors).toEqual([]);
});

test("demo workspace loads with seeded data", async ({ page }) => {
  const errors = watchErrors(page);
  await page.context().clearCookies();
  await page.goto("/");
  await page.getByRole("button", { name: "Open demo" }).click();
  await expect(page.getByText("Demo workspace")).toBeVisible();
  await expect(page.getByText("Teacher to Data Analyst (demo)")).toBeVisible();
  await nav(page, "Learning plan").click();
  await expect(page.getByText("Week 1", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
