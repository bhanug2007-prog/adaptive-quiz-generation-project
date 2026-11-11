# Publishing updates

## Future updates and deployment

Push application source, database migrations, tests, documentation, dependency
manifests/lockfiles, required static assets, and deployment configuration to this
repository whenever those files change, including when preparing a deployment.
Keep configuration templates such as `.env.example` in Git; configure real secrets
through the hosting provider's environment settings.

From the repository root, review and publish an update with:

```powershell
git status --short
git diff
# Run the relevant tests and build described in adaptiveiq/README.md.
git add .
git diff --cached --stat
git diff --cached
git commit -m "Describe the update"
git push origin main
```

Review the staged diff for private data before committing. The `.gitignore` rules
keep local secrets, databases, logs, dependencies, generated builds and large model
weights out of normal staging. Do not use `git add -f` to bypass those rules.

For deployment instructions, see [deployment documentation](adaptiveiq/docs/DEPLOYMENT.md)
and the provider-specific files under [adaptiveiq/deploy](adaptiveiq/deploy).
The deployment environment should install dependencies, build the frontend, and
apply the required database migrations after backing up production data. Model
weights should be supplied separately through the configured model host.

Pushing updates publishes code to GitHub. Deployment is a separate step unless a
hosting service has been explicitly connected to deploy this repository automatically.
