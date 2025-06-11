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
        stage('Inject .env from Jenkins Secret File') {
            // when {
            //     branch 'main'
            // }
            steps {
                withCredentials([file(credentialsId: 'jatin_env', variable: 'ENV_FILE1')]) {
                    // Clean up any existing .env file
                    sh 'rm -f .env'
                    // Copy the injected .env file
                    sh 'cp $ENV_FILE1 .env'
                }
            }
        }
        stage('Setup Python Env & Install Dependencies') {
            // when {
            //     branch 'main'
            // }
            steps {
                sh '''
                python3 -m venv venv
                source venv/bin/activate
                pip install --upgrade pip
                pip install -r requirements.txt
                '''
            }
        }
        stage('Login to AWS ECR') {
            steps {
                script {
                    // Authenticate to AWS ECR using the AWS CLI and Jenkins credentials
                    withCredentials([usernamePassword(credentialsId: 'aws-credentials', usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {
                        sh """
                            aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${DOCKER_REGISTRY}
                        """
                    }
                }
            }
        }
    }
}