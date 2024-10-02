# EagleEye AWS Infrastructure Automation

This project automates the creation and management of AWS infrastructure components including S3 buckets, EC2 instances, Target Groups, Load Balancers, and Auto Scaling Groups using Python and Boto3.

## Table of Contents

- [Project Overview](#project-overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)


## Project Overview

The EagleEye project demonstrates how to automate the provisioning of AWS resources for a web application. The script performs the following tasks:

1. Creates an S3 bucket and uploads files from a specified folder.
2. Launches an EC2 instance with a user-defined configuration.
3. Creates a Target Group and attaches the EC2 instance to it.
4. Sets up an Internet-facing Load Balancer and attaches it to the Target Group.
5. Registers the EC2 instance with the Target Group.
6. Creates an Auto Scaling Group to manage the EC2 instances.

## Prerequisites

Before running this project, ensure you have the following:

- Python 3.7 or higher installed.
- Boto3 library installed (`pip install boto3`).
- AWS CLI configured with appropriate IAM permissions.
- An existing SSH key pair in the specified region.

## Installation

1. **Clone the repository**:
    ```bash
    git clone https://github.com/Gani-23/Monitoring
    cd Monitoring
    ```

2. **Install required Python packages**:
    ```bash
    pip install boto3
    ```

3. **Configure AWS CLI**:
    Ensure you have configured the AWS CLI with your credentials:
    ```bash
    aws configure
    ```

## Usage

1. **Edit configuration parameters**:
    Modify the `process` function and other configuration parameters in the script to match your AWS setup (e.g., bucket name, folder path, AMI ID, key pair name).

2. **Run the script**:
    Execute the script to create and configure your AWS infrastructure:
    ```bash
    python Eagleeye.py
    ```



