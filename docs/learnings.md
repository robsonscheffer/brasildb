# What this prototype taught

Written 2026-11-02, when the prototype was parked. For whoever rebuilds it.

## Keep

- **Parquet plus DuckDB, with a table contract.** `catalog.yaml` names every table and column in the
  Base dos Dados style; the views in `sql/views/` answer each question in SQL ([#1](https://github.com/robsonscheffer/brasildb/pull/1)).
- **Resume from the lake, not from a state file.** Rerunning the same command fixes any failure: the
  full second-round collect (514,464 sections, 11.7 hours) had 135 errors, all fixed by one rerun.
- **A proof check per section.** Votes in the log equal the official turnout in 496,464 sections; the
  1,429 mismatches are replacement urnas. A parse change that breaks this check is wrong.
- **Mock data first for page design.** The walk was designed on mock files marked `"mock": true`
  ([#20](https://github.com/robsonscheffer/brasildb/pull/20)), then moved to real data.
- **Small static files.** The full-day map fits in under 1 MB ([#25](https://github.com/robsonscheffer/brasildb/pull/25)),
  each state's town file in under 33 KB gzip ([#35](https://github.com/robsonscheffer/brasildb/pull/35)).
- **A SQL audit of every published fact.** It found nine wrong facts on the live site, fixed the same
  day ([#39](https://github.com/robsonscheffer/brasildb/pull/39)).

## Change on a restart

- **Review and CI from the first PR.** 66 PRs merged in five days with no review and no tests on PRs;
  the only workflow runs on push to `main`, checks the site files and deploys them. The nine wrong facts were caught after publishing, not before.
- **Do not commit generated site data.** `docs/site/data/` holds 6,260 generated files (55 MB); the
  repo pack is 74 MB. Build them in the deploy, or serve them from object storage.
- **Plan the site as a home with cases.** The site was built for one subdomain and one case, so a
  second case means moving paths, the domain, canonical tags and the sitemap.
- **Pick the case before the data.** The plans grew from one case to five new datasets in four days
  ([PR #63](https://github.com/robsonscheffer/brasildb/pull/63)). Each new dataset should come from a
  question a page will answer.
- **Fix the flaky test.** `test_rate_limiter_spaces_requests` depends on timing and fails under load.
- **Add a licence on day one,** for the code and the data files.

## Facts found

- TSE answers about 100 requests per second per IP; 40 per second was safe for a full day.
- The log times are the urna's clock. Each town's offset from Brasília comes from its own first votes,
  because polls open at 08:00 Brasília everywhere; western Amazonas is -2 and Fernando de Noronha
  +1 ([#2](https://github.com/robsonscheffer/brasildb/pull/2)).
- Each section's count time comes from the BU files ([#57](https://github.com/robsonscheffer/brasildb/pull/57), [#58](https://github.com/robsonscheffer/brasildb/pull/58)).
- A full national collect runs at about 12 sections per second when parsing in worker processes
  ([#4](https://github.com/robsonscheffer/brasildb/pull/4)).

## Open questions

- An independent public count of votes after 17:00 found 280 more than this lake. The cause was not
  found.
- The first round was collected only for a sample and one town.
- The full collect as a scheduled cluster job was never built; it ran on a laptop.
