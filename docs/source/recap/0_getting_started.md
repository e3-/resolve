# 🏃‍♀️ 0. Getting Started

```{article-info}
:date: Sept 14, 2023
:read-time: 60 min read
:class-container: sd-p-2 sd-outline-muted sd-rounded-1
```

## Getting set up

If you can answer yes to all these questions, you are set up!

* Do you have access to E3's Github? If not, ask the Platforms Team (Karl and Dyami)
* Did you ask IT to set up an EC2 Instance yet? If not, follow the instruction from this teams post [here](https://teams.microsoft.com/l/message/19:63c1ea9380ef47bdb20a670efc3b5391@thread.skype/1727973030446?tenantId=4ecc8387-acae-4b64-8641-e32056145263&groupId=90cb82ef-4a8a-4379-a1e1-2b6712bfe2d6&parentMessageId=1727973030446&teamName=Models&channelName=General&createdTime=1727973030446) (or go directly to the asana page [here](https://app.asana.com/0/1207374357427622/1207374762698084).
* Do you have Anaconda on your laptop or EC2 instance?
* If using the cluster, did you get the following permissions from Pete Ngai (IT Manager)?
  * AWS?
  * Front Egg?
  * Datadog?


[//]: # (![]&#40;../_images/ui_tab_names_and_locations.png&#41;)

##  🖥️ 🔨 Where do I run RECAP?
* There are 3 main ways to run RECAP: 
  * (1) Locally (on your laptop), 
  * (2) on an AWS EC2 instance (remote desktop), or 
  * (3) on the cluster.

* For a project, an EC2 instance is used to perform initial model set-up and to run preliminary cases to confirm
that the system is behaving as expected.

* Once that stage is completed, the cluster may be used to run many cases on the cloud. Coordinate with your Technical Lead to determine if this is necessary for your project.

* RECAP should rarely, if ever, be run locally.

The general work flow looks like this.

![](../_images/setup_workflow.png)

Below is a primer on each type; more detailed set-up instructions are provided in the [3. Running RECAP section](3_running_model.md).

:::::{grid} 3
:padding: 0
:gutter: 2


::::{grid-item-card} Locally

:::{dropdown} Details
:margin: 0
* ❗RECAP should rarely, if ever, be run locally
* One exception may be to complete the [RECAP homeworks using the toy model](toy_model.md)

:::

::::


::::{grid-item-card} EC2 Instance

:::{dropdown} Details
:margin: 0
* AWS EC2 instances are remote desktops that enable E3 to (1) Size instances according to project needs and (2) Utilize a shared (Z:/) drive.
* For a new project, you will have to request to be assigned an EC2 instance
* **Reach out to Pete to request an EC2 instance.**
* [EC2 instance assignments are tracked here](https://app.asana.com/0/1207374357427622/1207374762698084).
* An EC2 instance is used to perform initial model set-up and to run preliminary cases to confirm
that the system is behaving as expected.



:::

::::

::::{grid-item-card} The Cluster

:::{dropdown} Details
:margin: 0
* The cluster provides the most scalable way to run RECAP (and RESOLVE).
* Users should first confirm the model behaves as expected on an EC2 instance before migrating runs onto the cluster.
* A new project must request that someone on the Platforms team (Karl, Dyami) set up a new cluster instance.
* Users will interact with the cluster principally through the `cloud_runner.ipynb` notebook. 
* You will need AWS permissions to interact with the cluster.
* **If you do not have AWS credentials (if you do, there is an AWS tile on your Okta home page): Put in a ticket with [WilldanIT](https://helpdesk.willdan.com) 
to add a new user's Willdan Email Addresses to the AD group: "E3 Developer". Do not mention AWS in the request.** 
* **[Instructions for interacting with the cluster are here](https://docs.ethree.com/en/latest/analytics/cloud/resolve.html)**.


:::
:::::

## 👷🔨 One-Time Setup

Please begin your setup by following the One-time setup instructions here: [](../quick_start).


### 📂 🔨 Data Setup

The Recap 3.0 code (`kit`) is stored on GitHub but example data is stored on Sharepoint. Click the button below to
download data and move the folder as it is to your master `“kit”` directory.

::::{card} Note that it is recommended to download this data when starting a new project.

This way technical leads and analysts will have a working model that can serve as a helpful reference with example
inputs and profiles which they can gradually replace with real project data.

:::
```{button-link} https://ethreesf.sharepoint.com/sites/Models/Shared%20Documents/Forms/AllItems.aspx?id=%2Fsites%2FModels%2FShared%20Documents%2FRecap%2F%5FRecap%20START%20FOLDER&p=true&ga=1
:color: primary
:outline: 
{octicon}`link-external;1em;sd-text-info` Navigate to SharePoint
```
:::

::::

<br>
