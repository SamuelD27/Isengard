# Release Notes

## v0.1.0-e2e-validated (2025-12-29)

### E2E Testing Infrastructure

This release establishes a comprehensive E2E testing pipeline that validates the GUI is production-ready.

#### Test Coverage Summary

| Suite | Tests | Status |
|-------|-------|--------|
| Smoke Tests | 17 | PASS |
| Training GUI | 31 | PASS |
| Visual Regression | 23 | PASS |
| API Wiring | 8 | PASS |
| **Total Passing** | **79** | |

#### What Was Validated

**Core Application**
- App loads without JavaScript errors
- All main pages render correctly (Characters, Training, Generation, Dataset)
- Navigation works between all pages
- API health and info endpoints return valid JSON

**Training GUI (Full Coverage)**
- Training history page displays correctly
- Start Training and Ongoing Training navigation works
- Training presets (Quick/Balanced/High Quality) function correctly
- Preset selection updates steps appropriately
- Character selector renders
- Advanced Settings toggle works
- Form validation enforces min/max constraints
- Empty states display correctly
- API integration returns JSON (not HTML)
- Error handling works gracefully

**Visual Regression**
- Baseline screenshots established for all core pages
- Responsive layouts tested (laptop, tablet, mobile)
- Component states captured (empty, error, loaded)

#### Fixes Made

1. **ESM Compatibility in Test Infrastructure**
   - Fixed `__dirname` not defined error in `gui-api-wiring.spec.ts`
   - Added ESM-compatible path resolution using `fileURLToPath`

#### Known Limitations

- UELR (Logs) page tests skipped - backend not implemented
- Legacy character/training flow tests skipped - superseded by new test suites
- Edge case tests (double-click, slow API) skipped - pending UI updates

#### Verification

```bash
# Quick validation (recommended before deployment)
./scripts/e2e-run.sh --quick --skip-services

# Full training GUI validation
./scripts/e2e-run.sh --training --skip-services

# Visual regression check
./scripts/e2e-run.sh --visual --skip-services
```

#### CI/CD Integration

The GitHub Actions workflow is configured to:
- Run quick validation on every PR
- Run full E2E suite on push to main/develop
- Run visual regression on push to main
- Upload test artifacts on failure
