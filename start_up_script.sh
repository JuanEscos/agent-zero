apt update

apt install -y git tmux fish vim htop libgl1-mesa-glx

wget https://gist.githubusercontent.com/zmonoid/1e660de965747c9a70bffb80b520f6bd/raw/d259412cee7a8c64071dd8d503ec936c77b9f3ff/requirements.txt

pip install -r requirements.txt

pip install torch==1.6.0+cu101 torchvision==0.7.0+cu101 -f https://download.pytorch.org/whl/torch_stable.html