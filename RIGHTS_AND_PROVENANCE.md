# Rights and provenance

This demonstration was prepared specifically for Subba Cecchetto, with AI assistance, as a new implementation of standard portfolio-analysis concepts. Human review remains responsible for the public claims and any later changes.

## Material included

- Newly written Python source, tests, validation tooling and explanatory text.
- Artificial returns created locally from a fixed NumPy random seed and explicitly declared constants.
- CSV, JSON and PNG artifacts generated from those artificial returns.
- Validation records from actual small local test/demo executions. Local filesystem prefixes in diagnostic logs are replaced by neutral labels; warning/error content is retained.

No internship source, client material, real instrument identifiers, price history, holdings, proprietary configuration, institutional report, credentials, third-party images or copied code is included. The earlier project's 65,807-allocation count is mentioned only to distinguish that historical project from this separate experiment; its source manifest is not redistributed here. Publication of this repository does not imply institutional endorsement.

## Algorithmic sources

The algorithmic rules are the standard definitions explicitly described in README.md and the fixed Config in src/portfolio_demo.py: a finite long-only weight grid, full-investment constraints, chronological data separation, annual rebalancing with proportional costs, sample return/volatility, drawdown from an initial endowment and a fractionally weighted empirical loss tail. The code was written for this demonstration from those definitions; no specific published implementation or paper's empirical result is reproduced.

NumPy and matplotlib are external dependencies, not vendored source. Their own licenses and those of their dependencies remain applicable. The repository does not grant rights over those packages or third-party data.

## Licensing status

No MIT, Apache or other broad source/data license is assigned by this package. No external publication or reuse permission for the original internship project is inferred. The repository owner should make any later licensing decision based on their actual rights; until an explicit license is added, this document is a provenance statement rather than an unrestricted reuse grant.


## Publication scope confirmed by the owner

On 5 November 2026 the owner authorized public publication of the verified demonstration and its use for independent technical inspection and execution. For the selected original thesis and RO-01 modules, the owner separately confirmed their rights of diffusion. This scope does not include internship materials, proprietary market data or trained weights. No general MIT, Apache or other open-source reuse licence has been selected automatically.
