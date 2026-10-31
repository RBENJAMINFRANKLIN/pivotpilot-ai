# Wispr Flow (dictation) demo

Wispr Flow is a system-wide dictation tool: it types what you say into whichever text field has focus. PivotPilot
does not use any Wispr Flow API (none is assumed). Every important input is a normal text field, so dictation works
the same as typing.

**Fields that accept dictation**: resume text, job description, goal and profile fields, interview answers,
project notes, and the command box at the top of every page.

## Demo workflow (command box)

1. Open any page and click the command box ("Type or dictate…").
2. Hold your Wispr Flow hotkey and say: *"Um, I can study about eight hours a week now."*
   Wispr Flow types the text; filler words are fine.
3. Press **Enter** (or **Interpret**). The backend parses the text into a proposed action and validates it:
   > Proposed change: Change weekly study time to 8 hours. Weekly study hours: 6 → **8**
4. Click **Confirm**. Changes are never applied without confirmation.
5. The backend applies the change through the same rules as the normal forms and reports the actual result:
   > Done: Change weekly study time to 8 hours.

Other phrases to try:

| Say | Proposed action |
|---|---|
| "My deadline is the end of June" | Set deadline |
| "I only want free courses" / "My budget is $200" | Set budget |
| "I want to become a product manager" | Change target role |
| "I finished today's task" / "I finished the SQL practice" | Mark the matching plan task complete |
| "I applied for the junior data analyst role at Acme" | Add an application |
| "Acme rejected me" / "I got an interview with Contoso" | Update that application's status |
| "Quiz me on SQL" | Start a SQL checkpoint quiz |
| "Please regenerate my plan" | New plan version (completed tasks kept) |

Invalid values are caught before confirmation (e.g. "200 hours a week" → "Weekly hours must be between 1 and 80").
The execute endpoint re-validates, so a tampered request cannot skip the checks.

**Tested here**: the parsing, validation, confirmation and execution flow, by automated API, component and browser
tests using typed text. **Not tested here**: Wispr Flow itself on a real device (it needs a desktop OS with the app
installed). Please try it on your PC.
