# Supabase database certificate authority

`supabase-root-2021.crt` is the public Supabase Root 2021 CA certificate, downloaded
over verified HTTPS from:

https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt

Certificate DER SHA-256:

`807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa`

The connection verified the CA chain and pooler hostname using this certificate on
2026-11-09. It contains no private key or database credentials.

The native `.env` connection uses an absolute `sslrootcert` path. For a hosted container,
mount this certificate read-only and use its container path in the connection URL.
`compose.supabase.yaml` mounts this directory at `/srv/lustcode/certs` read-only in the
migrator, API, and worker. The native URL keeps its host certificate path; the Docker
URL uses `/srv/lustcode/certs/supabase-root-2021.crt`.
