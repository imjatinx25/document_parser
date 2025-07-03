pipeline {
    agent any

    triggers {
        githubPush()
    }

    environment {
        AWS_REGION = 'ap-south-1'
        DOCKER_REGISTRY = '676206929524.dkr.ecr.ap-south-1.amazonaws.com'
        DOCKER_IMAGE = 'dev-orbit-pem'
        DOCKER_NAME = "JATIN"
        DOCKER_TAG = "${DOCKER_IMAGE}:${DOCKER_NAME}${BUILD_NUMBER}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Load Environment from Jenkins Secret') {
            steps {
                withCredentials([file(credentialsId: 'jatin_env', variable: 'ENV_FILE2')]) {
                    sh '''
                        echo "Loading environment variables"
                        rm -f .env
                        cp $ENV_FILE2 .env
                        chmod 644 .env
                    '''
                }
            }
        }

        stage('Login to AWS ECR') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'aws-credentials', usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {
                    sh '''
                        aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID
                        aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY
                        aws configure set default.region ${AWS_REGION}
                        aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${DOCKER_REGISTRY}
                    '''
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                sh """
                    docker build -t ${DOCKER_TAG} .
                """
            }
        }

        stage('Tag Docker Image for ECR') {
            steps {
                sh """
                    docker tag ${DOCKER_TAG} ${DOCKER_REGISTRY}/${DOCKER_TAG}
                """
            }
        }

        stage('Push Image to ECR') {
            steps {
                sh """
                    docker push ${DOCKER_REGISTRY}/${DOCKER_TAG}
                """
            }
        }

        stage('Stop & Remove Old Container on Port 8001') {
            steps {
                sh '''
                    container_id=$(docker ps -q --filter "publish=8001")
                    if [ -n "$container_id" ]; then
                        docker stop $container_id
                        docker rm $container_id
                        echo "Old container stopped and removed."
                    else
                        echo "No container running on port 8001."
                    fi
                '''
            }
        }

        stage('Run New Container on Port 8001') {
            steps {
                withCredentials([
                    file(credentialsId: 'jatin_env', variable: 'ENV_FILE2'),
                    usernamePassword(credentialsId: 'aws-credentials', usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')
                ]) {
                    script {
                        def envVars = readFile(env.ENV_FILE2).split("\n")
                            .findAll { it.contains("=") }
                            .collect { "-e ${it.trim()}" }
                            .join(" ")

                        sh """
                            docker run -d -p 8001:8001 \
                                ${envVars} \
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
                message: "✅ Build SUCCESSFUL: ${env.JOB_NAME} [${env.BUILD_NUMBER}]",
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
