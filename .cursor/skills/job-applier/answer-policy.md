# Answer policy

Use facts in this order:

1. Exact profile field (name, email, phone, school, links, work authorization, sponsorship).
2. Exact saved question in `profile/answers.yaml`.
3. A similar saved question only when the match is clearly ahead of the next candidate. Mark it for a check when the match is weaker.
4. One model call for the remaining questions on that application, and only when `OPENAI_API_KEY` is set.

The model may return null. Keep that null. Do not guess GPA, visa sponsorship, citizenship, graduation date, or demographics.

EEO and demographic selects default to the option that declines to self-identify.

When the user saves a custom answer in review, write that question and answer into `profile/answers.yaml`. Do not write name, email, phone, resume, or profile links into the answer bank.

Identity corrections belong in `profile/profile.yaml`.
