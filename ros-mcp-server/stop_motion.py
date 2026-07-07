import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import time

stop_script = """def stop_motion():
  stopl(2.0)
end
"""

def main():
    rclpy.init()
    node = rclpy.create_node('stop_ur_motion')
    pub = node.create_publisher(String, '/urscript_interface/script_command', 10)
    msg = String()
    msg.data = stop_script
    
    time.sleep(1.0) # Wait for connections
    
    pub.publish(msg)
    node.get_logger().info("Published URScript stop command")
    
    time.sleep(1.0)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
