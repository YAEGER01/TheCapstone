# Reports Tracker

Source of truth for report content: `_archive/old-backups/FROMGROUP/ISUCauFA_Report_Samples.docx`
(49 sample pages: 47 layouts + X1 + X2). Every sample page becomes one **new**
report type under the **New Reports** group in Treasurer → Reports Management.
Legacy report types are never removed or replaced.

Layout legend: **LP-1** detail listing · **LP-2** summary rollup ·
**LP-3** workflow listing · **LP-4** member statement ·
**LP-5** financial statement.

## Membership and Collection

| Code | Report | Layout | Status |
|------|--------|--------|--------|
| A1 | Membership Fee Report | LP-1 | DONE |
| A2 | Monthly Dues Collection Report | LP-1 | DONE |
| A3 | Payment Status Report | LP-1 | DONE |
| A4 | Outstanding Balance Report | LP-4 | DONE |
| A5 | Collection Summary Report | LP-2 | DONE |

## Aid

| Code | Report | Layout | Status |
|------|--------|--------|--------|
| AID1 | Aid Application Report | LP-3 | DONE |
| AID2 | Aid Approval Report | LP-3 | DONE |
| AID3 | Aid Disbursement Report | LP-3 | DONE |
| AID4 | Aid Releasing Report | LP-3 | DONE |
| AID5 | Aid Beneficiary/Recipient Report | LP-1 | DONE |
| AID6 | Pending Aid Report | LP-3 | DONE |
| AID7 | Pending Aid Audit Report | LP-3 | DONE |
| AID8 | Aid Financial Summary Report | LP-2 | DONE |
| AID9 | Releasing by Recipient Report | LP-4 | DONE |
| AID10 | Releasing Summary Report | LP-2 | DONE |
| AID11 | Unreleased Approved Aid Report | LP-3 | DONE |

## Donation and Disbursement

| Code | Report | Layout | Status |
|------|--------|--------|--------|
| D1 | Cash Donation Report | LP-1 | DONE |
| D2 | Donation Disbursement Report | LP-1 | DONE |
| D3 | General Disbursement Report | LP-1 | DONE |
| D4 | Disbursement Summary Report | LP-2 | DONE |

## Control and Exception

| Code | Report | Layout | Status |
|------|--------|--------|--------|
| F1 | Pending Transactions Report | LP-3 | DONE |
| F2 | Pending Audit Report | LP-3 | DONE |
| F3 | Pending Approval Report | LP-3 | DONE |
| F4 | Pending Disbursement Report | LP-3 | DONE |
| F5 | Incomplete Documentation Report | LP-3 | DONE |
| F6 | Audit Exceptions Report | LP-3 | DONE |
| F7 | Discrepancy Report | LP-1 | DONE |

## Bank and Cash 

| Code | Report | Layout | Status |
|------|--------|--------|--------|
| G1 | Withdrawal Report | LP-1 | DONE |
| G2 | Bank Withdrawal Summary Report | LP-2 | DONE |
| G3 | Cash Position Report | LP-5 | DONE |
| G4 | Fund Balance Report | LP-5 | DONE |
| G5 | Cash Flow Summary Report | LP-5 | DONE |

## Ledgers and Financial Summaries

| Code | Report | Layout | Status |
|------|--------|--------|--------|
| H1 | General Journal | LP-1 | DONE |
| H2 | General Ledger | LP-1 | DONE |
| H3 | Member Subsidiary Ledger | LP-4 | DONE |
| H4 | Aid Subsidiary Ledger | LP-1 | DONE |
| H5 | Cash Ledger | LP-1 | DONE |
| H6 | Donation Ledger | LP-1 | DONE |
| H7 | Disbursement Ledger | LP-1 | DONE |
| H8 | Monthly Financial Summary | LP-5 | DONE |
| H9 | Quarterly Financial Summary | LP-5 | DONE |
| H10 | Annual Financial Summary | LP-5 | DONE |

## Newly Recommended

| Code | Report | Layout | Status |
|------|--------|--------|--------|
| N1 | Member Masterlist / Registration Report | LP-1 | DONE |
| N2 | Bank Reconciliation Report | LP-5 | DONE |
| N3 | Budget vs Actual Report | LP-2 | DONE |
| N4 | User Access & Activity Log | LP-1 | DONE |
| N5 | Officer Turnover Report | LP-3 | DONE |

## Panel-added

| Code | Report | Layout | Status |
|------|--------|--------|--------|
| X1 | Retirement and Death Donation Report | LP-1 | DONE |
| X2 | Deposit Report | LP-1 | DONE |

## Conventions for each new type

- One `<option>` per sample page under the **New Reports** optgroup; value is the
  lowercase code (`a1`, `a2`, `aid1`, …); legacy options untouched.
- `RPT.REPORTS` entry carries `refCode` (e.g. `A1`), `sheetTitle` (sample title),
  and a `sample` spec: `scope`, `notes`, `params` — rendered 1:1 (letterhead with
  SEC Reg. No. 2692, metadata, REPORT PARAMETERS, REPORT DATA, NOTES, audit line).
- Live database data only; anything the system does not track renders `—` with a
  note instead of synthetic data.
- Wide grids (>4 columns) use the `sample-grid` fixed layout so sheets never
  overflow A4 (screen preview and print/PDF alike).
- Each type ships with a `core_system/tests_sample_<code>.py` contract test.
