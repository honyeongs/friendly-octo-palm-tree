# Third-Party Notices

Runtime dependency versions, reported licenses, and original notice checksums are recorded in `docs/DEPENDENCIES.json`. Original package license/notice files are preserved in `third_party/`. The CycloneDX package inventory is `docs/SBOM.cdx.json`.

Lucide ISC and Feather MIT icon notices are in `src/netsec/web/assets/LUCIDE-LICENSE.txt`. System fonts are referenced but not bundled.

Psycopg and psycopg-binary report LGPL-3.0-only. Certifi reports MPL-2.0. These components have obligations beyond merely keeping a notice when conveying covered binaries or modified files. Read their original terms and `docs/LEGAL_REVIEW.md` before distributing a container or installer. Keep their source availability/replacement rights intact. The dependency notices do not grant a project-wide license to the original application code.

This inventory excludes complete OS/container images, developer tools and unenumerated native libraries bundled inside binary wheels. Audit those artifacts separately before redistribution. No representation of universal copyright, patent, trademark or regulatory clearance is made.
