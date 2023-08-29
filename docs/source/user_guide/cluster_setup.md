(cluster_setup)=
# Using the Kubernetes Cluster

## Setting Up Cluster Usage

### 1. Install AWS CLI

Install the AWS Command-Line-Interface (CLI) by following the instructions here: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

### 2. Install kubectl

Install the kubectl software by following the instructions here: https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/ 
(or, if using a Mac, here: https://kubernetes.io/docs/tasks/tools/install-kubectl-macos/).

### 3. Configure AWS Access

#### Configure AWS CLI
Once logged in to your workstation open the Windows PowerShell command window and type in the following commands in the following commands to configure the AWS CLI:
```commandline
aws configure set region us-west-2
aws configure set sso_start_url https://d-9267736486.awsapps.com/start
aws configure set sso_region us-west-2
aws configure set sso_account_id 876451484466
aws configure set sso_role_name DataUserAccess
```

If you were granted a different AWS Role, you can enter that in the last line instead (e.g. PowerUserAccess). The default
is DataUserAccess, so unless you were specifically told otherwise, enter as above. 

#### Authenticating with AWS
Before you can issue any commands you must authenticate with AWS. This is done by via Okta using your Willdan AD 
credentials. To start the authentication process issue the following command:

```commandline
aws sso login
```

This will open your default browser window and re-direct you to Okta log-in page where you can enter your credentials. 
After authenticating with Okta you will be redirected back to AWS where you can approve your AWS CLI access. Once the 
process is complete you may close the browser window.

You can test that the authentication was successful by issuing the following command:

```commandline
aws s3 ls s3://e3x-cpuc-irp-data/
```

You should see an output similar to this:

```commandline
                           PRE inputs/
                           PRE outputs/
                           PRE runs/
```

### 4. Configure Argo Access

#### Configure Kubernetes CLI

Before you proceed with this step you need to first configure your AWS CLI and authenticate with AWS (see previous 
steps). Once these steps are completed you can issue following command in order to create Kubernetes context:

```commandline
aws eks update-kubeconfig --name e3x-enkap-main --alias e3x-enkap-main
```

To test if this was successful issue the following command:

```commandline
kubectl -n cpuc-irp get pods
```

The output should look similar to this:

```commandline
NAME                                                 READY   STATUS    RESTARTS      AGE
argo-workflows-server-5f96bf68cf-7fdfv               1/1     Running   0             14d
argo-workflows-workflow-controller-d6cf98c86-xl7cc   1/1     Running   1 (43h ago)   14d
```

It is recommended to set the default workspace to your project, to do so issue the following command:

```commandline
kubectl config set-context --current --namespace cpuc-irp
```

This way all the commands you issue will execute in the cpuc-irp namespace by default (you can skip the -n cpuc-irp 
parameter), you can test by issuing following command:

```commandline
kubectl get pods
```

The output should be identical to the command issued earlier.

## Using the Cluster

### Configuring Your Project

Before submitting any jobs to the cluster, you must configure your project. Go to your root NMT directory, activate your
conda environment, and run the following command:

```commandline
nmt init enter-a-project-name-here

# e.g. for CPUC IRP users
nmt init cpuc-irp
```

Additional options are available for configuring your project and the default values can be viewed by running:

```commandline
nmt init --help
```

For example, if you want to customize where your "data folder" is, use an "extras" module by default, and use Gurobi as
your solver, you can do the following:

```commandline
nmt init cpuc-irp --data="path/to/my/data/folder" --extras="cpuc_irp" --solver="gurobi"
```


### Submitting a Remote NMT Run

In order to submit a remote run, enter the following command:

```commandline
nmt submit
```

By default, this will sync all files from the data folder that was specified during `nmt init` to a cloud storage bucket
before submitting all cases listed in your data folder under `settings/resolve/cases_to_run.csv` to be run on the cloud. 
This command will output a **Run ID** that can be used to locate this run in Argo UI and Datadog.

You can get the additional available options by issuing this command:

```commandline
nmt submit --help
```

### Downloading Outputs of a Remote NMT Run

For the remote runs the data can not be automatically written to a local (shared) drive and must be explicitly 
downloaded. To do so you can issue the following command:

```commandline
nmt download-outputs
```

This will download the results of all the previous runs to an appropriate subdirectory of the current folder. Note that 
it is not necessary to wait for all the cases to complete before downloading the outputs. If you issue the command 
before all cases are complete you will only get the outputs of the completed cases. Note that any subsequent run of 
this command **will override any local changes**.

#### What to do if `download-outputs` doesn't work

If the `nmt download-outputs` command results in errors, you can manually download the results from a specific 
submission using the **Run ID** that was printed when you submitted your runs by running the following command from
your root NMT directory:

```commandline
aws s3 sync s3://e3x-your-project-name-data/runs/your-run-id/outputs/reports reports/

# e.g., for CPUC IRP with Run ID jsmith20230815.1
aws s3 sync s3://e3x-cpuc-irp-data/runs/jsmith20230815.1/outputs/reports reports 
```

