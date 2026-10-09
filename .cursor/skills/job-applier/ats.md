# Application boards

Classify the apply link, not the Simplify link, when both are present.

- Greenhouse: `job-boards.greenhouse.io/{token}/jobs/{id}` or `boards.greenhouse.io/{token}/jobs/{id}`, either with an optional `.eu` before `.greenhouse.io`
  - Embed links: `.../embed/job_app?for={token}&token={id}`. An embed link without `for` is resolved by following its redirect.
  - Questions: `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}?questions=true`. EU boards use the same API host.
- Lever: `jobs.lever.co/{token}/{uuid}` with an optional `/apply`
- Ashby: `jobs.ashbyhq.com/{token}/{uuid}` with an optional `/application`

Other hosts, including Workday and iCIMS, stay in the manual list. Do not automate those forms.

Lever and Ashby question text comes from a read-only page scan when the public posting has no form. That scan does not type and does not submit. Filling happens only after the user saves and chooses "Save and open filled form".
