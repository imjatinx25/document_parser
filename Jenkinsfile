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
                withCredentials([file(credentialsId: 'jatin_env', variable: 'ENV_FILE2')]) {
                    sh 'echo $ENV_FILE2'
                    // Clean up any existing .env file
                    sh 'rm -f .env'
                    // Copy the injected .env file
                    sh 'cp $ENV_FILE2 .env'

                    sh 'cat .env'
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
        stage('Build Docker Image') {
            steps {
                script {
                    // Build Docker image
                    sh """
                        docker build -t ${DOCKER_TAG} .
                    """
                }
            }
        }
        stage('Tag Docker Image') {
            steps {
                script {
                    // Tag the Docker image with the correct repository path
                    sh """
                        docker tag ${DOCKER_TAG} ${DOCKER_REGISTRY}/${DOCKER_TAG}
                    """
                }
            }
        }
        stage('Push Docker Image to ECR') {
            steps {
                script {
                    // Push the Docker image to AWS ECR
                    sh """
                        docker push ${DOCKER_REGISTRY}/${DOCKER_TAG}
                    """
                }
            }
        }
        stage('Stop and Remove Old Docker Container Running on Port 8001') {
            steps {
                script {
                    // Stop and remove the container running on port 8001
                    sh """
                        container_id=\$(docker ps -q --filter "publish=8001")
                        if [ -n "\$container_id" ]; then
                            docker stop \$container_id
                            docker rm \$container_id
                            echo 'Old container stopped and removed'
                        else
                            echo 'No container running on port 8001'
                        fi
                    """
                }
            }
        }
        stage('Run New Docker Container on Port 8001') {
            steps {
                script {
                    withCredentials([file(credentialsId: 'jatin_env', variable: 'ENV_FILE2'),
                                    usernamePassword(credentialsId: 'aws-credentials', usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {
                        sh """
                            # Login to AWS ECR with the credentials passed from Jenkins
                            aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${DOCKER_REGISTRY}

                            # Clean up any existing container on port 8001 if it exists
                            docker ps -q --filter publish=8001 | xargs -r docker stop | xargs -r docker rm

                            # Run Docker container on port 8001, pass AWS credentials and .env file to the container
                            docker run -d -p 8001:8001 \
                                --env-file $ENV_FILE2 \
                                -e AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
                                -e AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY} \
                                ${DOCKER_REGISTRY}/${DOCKER_TAG}
                        """
                    }
                }
            }
        }


    }
    post {
        success {
            slackSend (
                tokenCredentialId: 'slack_channel_secret',
                message: "✅ Build SUCCESSFUL: JATIN${env.JOB_NAME} [${env.BUILD_NUMBER}]",
                channel: '#jenekin_update',
                color: 'good',
                iconEmoji: ':white_check_mark:',
                username: 'Jenkins'
            )
        }
        failure {
            slackSend (
                tokenCredentialId: 'slack_channel_secret',
                message: "❌ Build FAILED: ${env.JOB_NAME} [${env.BUILD_NUMBER}]",
                channel: '#jenekin_update',
                color: 'danger',
                iconEmoji: ':x:',
                username: 'Jenkins'
            )
        }
        always {
            cleanWs()
        }
    }
}