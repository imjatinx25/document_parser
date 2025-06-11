pipeline{
    agent any

    triggers {
        githubPush()  // Trigger build on GitHub push
    }

    environment {
        BRANCH_NAME = "${env.BRANCH_NAME}"  // Correctly quote the variable
        AWS_REGION = 'ap-south-1'  // Set your AWS region
        DOCKER_REGISTRY = '676206929524.dkr.ecr.ap-south-1.amazonaws.com'  // ECR registry URL
        DOCKER_IMAGE = 'dev-orbit-pem'  // ECR repository and image name
        DOCKER_NAME = "JATIN"
        DOCKER_TAG = "${DOCKER_IMAGE}:${DOCKER_NAME}${BUILD_NUMBER}"  // Concatenate correctly
    }

    stages{
        stage('Checkout') {
                // when {
                //     expression { return  env.GIT_BRANCH == 'refs/heads/main' }
                // }
                steps {
                    checkout scm
                }
        }
    }
}