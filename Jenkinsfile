pipeline {
    agent any

    environment {
        AWS_REGION = 'ap-south-1'
        DOCKER_REGISTRY = '676206929524.dkr.ecr.ap-south-1.amazonaws.com'
        DOCKER_IMAGE = 'dev-orbit-pem'
        DOCKER_NAME = 'JATIN'
        DOCKER_TAG = "${DOCKER_NAME}${BUILD_NUMBER}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Inject .env from Jenkins Secret') {
            steps {
                withCredentials([file(credentialsId: 'jatin_env', variable: 'ENV_FILE2')]) {
                    sh '''
                        rm -f .env
                        cp $ENV_FILE2 .env
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

        stage('Build Docker Images via Docker Compose') {
            steps {
                sh '''
                    docker compose build
                '''
            }
        }

        stage('Tag & Push Images to AWS ECR') {
            steps {
                script {
                    def fullImageTag = "${DOCKER_REGISTRY}/${DOCKER_IMAGE}:${DOCKER_TAG}"

                    sh """
                        docker tag ${DOCKER_IMAGE}_web ${fullImageTag}
                        docker push ${fullImageTag}
                    """
                }
            }
        }

        stage('Stop Existing Containers') {
            steps {
                sh 'docker compose down || true'
            }
        }

        stage('Deploy via Docker Compose') {
            steps {
                sh 'docker compose up -d'
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
