# Release and DOI Workflow

## Development

```text
VS Code / Quarto
        ↓
      Git
        ↓
     GitHub
```

## Scholarly release

```text
Stable manuscript + code + metadata
        ↓
Git tag / GitHub Release
        ↓
Archival repository
        ↓
Persistent identifier / DOI
        ↓
Preferred citation
```

## Release checklist

- render the complete project;
- confirm clean Git status;
- update version number;
- update changelog/release notes;
- verify README reproduction instructions;
- verify citation metadata;
- verify license;
- remove secrets and restricted files;
- tag the release;
- create the remote release;
- archive the release in an appropriate repository;
- record the DOI;
- update the book/manuscript citation;
- test the archived artifact.

A DOI identifies an archived object. It does not imply peer review or methodological validity.
